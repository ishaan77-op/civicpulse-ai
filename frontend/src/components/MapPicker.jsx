import { useEffect, useMemo, useRef, useState } from 'react'
import {
  MapContainer,
  Marker,
  TileLayer,
  useMap,
  useMapEvents,
} from 'react-leaflet'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'

import markerIcon2x from 'leaflet/dist/images/marker-icon-2x.png'
import markerIcon from 'leaflet/dist/images/marker-icon.png'
import markerShadow from 'leaflet/dist/images/marker-shadow.png'

delete L.Icon.Default.prototype._getIconUrl

L.Icon.Default.mergeOptions({
  iconRetinaUrl: markerIcon2x,
  iconUrl: markerIcon,
  shadowUrl: markerShadow,
})

const NASHIK_CENTER = [20.0110, 73.7903]

// Approximate Nashik city bounds.
// These are intentionally broad so legitimate Nashik areas are not blocked.
const NASHIK_BOUNDS = {
  minLat: 19.85,
  maxLat: 20.25,
  minLng: 73.60,
  maxLng: 74.05,
}

function isInsideNashik(latitude, longitude) {
  return (
    latitude >= NASHIK_BOUNDS.minLat &&
    latitude <= NASHIK_BOUNDS.maxLat &&
    longitude >= NASHIK_BOUNDS.minLng &&
    longitude <= NASHIK_BOUNDS.maxLng
  )
}

function MapRecenter({ position, zoom = 15 }) {
  const map = useMap()

  useEffect(() => {
    if (position) {
      map.flyTo(position, zoom, {
        duration: 1,
      })
    }
  }, [map, position, zoom])

  return null
}

function LocationMarker({ position, onLocationSelect, icon }) {
  useMapEvents({
    click(event) {
      onLocationSelect?.({
        latitude: event.latlng.lat,
        longitude: event.latlng.lng,
      })
    },
  })

  if (!position) {
    return null
  }

  return (
    <Marker
      position={position}
      icon={icon}
      draggable
      eventHandlers={{
        dragend(event) {
          const marker = event.target
          const latlng = marker.getLatLng()

          onLocationSelect?.({
            latitude: latlng.lat,
            longitude: latlng.lng,
          })
        },
      }}
    />
  )
}

function LocateMeButton({ onLocate, loading }) {
  const map = useMap()

  const handleClick = () => {
    onLocate((position) => {
      map.flyTo(position, 16, {
        duration: 1.2,
      })
    })
  }

  return (
    <button
      type="button"
      onClick={handleClick}
      disabled={loading}
      style={{
        position: 'absolute',
        right: '12px',
        bottom: '24px',
        zIndex: 1000,
        width: '44px',
        height: '44px',
        borderRadius: '10px',
        border: '1px solid #ddd',
        background: '#fff',
        boxShadow: '0 2px 8px rgba(0,0,0,0.15)',
        cursor: loading ? 'wait' : 'pointer',
        fontSize: '20px',
      }}
      aria-label="Use my current location"
      title="Use my current location"
    >
      {loading ? '⏳' : '📍'}
    </button>
  )
}

function MapPicker({
  onLocationSelect,
  initialPosition = NASHIK_CENTER,
  zoom = 12,
}) {
  const [selectedPosition, setSelectedPosition] = useState(null)

  const [loadingLocation, setLoadingLocation] = useState(false)
  const [locationError, setLocationError] = useState('')

  const [selectedAddress, setSelectedAddress] = useState('')
  const [selectedPincode, setSelectedPincode] = useState('')
  const [loadingAddress, setLoadingAddress] = useState(false)

  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState([])
  const [searching, setSearching] = useState(false)
  const [searchError, setSearchError] = useState('')
  const [showSuggestions, setShowSuggestions] = useState(false)

  const [confirmed, setConfirmed] = useState(false)

  const searchTimeoutRef = useRef(null)
  const searchRequestRef = useRef(0)
  const addressRequestRef = useRef(0)

  const customIcon = useMemo(
    () =>
      L.divIcon({
        className: 'civicpulse-map-marker',
        html: `
          <div style="
            width: 34px;
            height: 34px;
            border-radius: 50% 50% 50% 0;
            background: #2563eb;
            transform: rotate(-45deg);
            border: 3px solid white;
            box-shadow: 0 3px 10px rgba(0,0,0,0.3);
            display: flex;
            align-items: center;
            justify-content: center;
          ">
            <div style="
              width: 10px;
              height: 10px;
              border-radius: 50%;
              background: white;
            "></div>
          </div>
        `,
        iconSize: [34, 34],
        iconAnchor: [17, 34],
      }),
    [],
  )

  /*
   * Reverse geocoding:
   *
   * Coordinates are the source of truth.
   * Address and pincode are only display information returned
   * by the geocoder.
   */
  const fetchAddress = async (latitude, longitude) => {
    const requestId = ++addressRequestRef.current

    setLoadingAddress(true)
    setSelectedAddress('')
    setSelectedPincode('')

    try {
      const params = new URLSearchParams({
        format: 'jsonv2',
        lat: String(latitude),
        lon: String(longitude),
        zoom: '18',
        addressdetails: '1',
      })

      const response = await fetch(
        `https://nominatim.openstreetmap.org/reverse?${params.toString()}`,
        {
          headers: {
            Accept: 'application/json',
          },
        },
      )

      if (!response.ok) {
        throw new Error('Reverse geocoding failed.')
      }

      const result = await response.json()

      if (requestId !== addressRequestRef.current) {
        return
      }

      const address = result.address || {}

      /*
       * Build a cleaner human-readable address.
       * We intentionally do NOT use result.display_name directly
       * because it can be extremely long.
       */
      const addressParts = [
        address.house_number,
        address.road,
        address.neighbourhood,
        address.suburb,
        address.city_district,
        address.city,
        address.town,
        address.village,
      ].filter(Boolean)

      const uniqueParts = [...new Set(addressParts)]

      setSelectedAddress(
        uniqueParts.length
          ? uniqueParts.join(', ')
          : result.display_name || '',
      )

      /*
       * Only show a pincode if Nominatim actually returned one.
       * Never invent or guess a pincode.
       */
      const postcode = address.postcode?.trim() || ''

      if (/^\d{6}$/.test(postcode)) {
        setSelectedPincode(postcode)
      } else {
        setSelectedPincode('')
      }
    } catch {
      if (requestId === addressRequestRef.current) {
        setSelectedAddress('')
        setSelectedPincode('')
      }
    } finally {
      if (requestId === addressRequestRef.current) {
        setLoadingAddress(false)
      }
    }
  }

  const selectLocation = (latitude, longitude) => {
    if (!isInsideNashik(latitude, longitude)) {
      setLocationError(
        'Please select a location within the Nashik area.',
      )
      return
    }

    const position = [latitude, longitude]

    setSelectedPosition(position)
    setConfirmed(false)

    setLocationError('')
    setSearchError('')

    fetchAddress(latitude, longitude)

    onLocationSelect?.({
      latitude,
      longitude,
    })
  }

  /*
   * Browser GPS
   */
  const detectLocation = (afterSuccess) => {
    if (!navigator.geolocation) {
      setLocationError(
        'Location detection is not supported by your browser.',
      )
      return
    }

    setLoadingLocation(true)
    setLocationError('')
    setSearchError('')

    navigator.geolocation.getCurrentPosition(
      (position) => {
        const { latitude, longitude } = position.coords

        if (!isInsideNashik(latitude, longitude)) {
          setLoadingLocation(false)

          setLocationError(
            'Your detected location is outside the Nashik area. Please select a Nashik location manually.',
          )

          return
        }

        selectLocation(latitude, longitude)

        setLoadingLocation(false)

        afterSuccess?.([latitude, longitude])
      },
      (error) => {
        setLoadingLocation(false)

        if (error.code === error.PERMISSION_DENIED) {
          setLocationError(
            'Location permission was denied. You can select a location manually on the map.',
          )
        } else if (error.code === error.POSITION_UNAVAILABLE) {
          setLocationError(
            'Your location could not be determined. Please select it manually.',
          )
        } else if (error.code === error.TIMEOUT) {
          setLocationError(
            'Location detection timed out. Please try again or select a location manually.',
          )
        } else {
          setLocationError(
            'Unable to detect your location. Please select it manually.',
          )
        }
      },
      {
        enableHighAccuracy: true,
        timeout: 10000,
        maximumAge: 60000,
      },
    )
  }

  /*
   * Search / autocomplete
   */
  const fetchSuggestions = async (query) => {
    const trimmedQuery = query.trim()

    if (trimmedQuery.length < 2) {
      setSearchResults([])
      setSearching(false)
      return
    }

    const requestId = ++searchRequestRef.current

    setSearching(true)
    setSearchError('')

    try {
      const params = new URLSearchParams({
        format: 'jsonv2',
        addressdetails: '1',
        limit: '7',
        countrycodes: 'in',

        /*
         * Bias the search strongly toward Nashik.
         */
        viewbox: '73.60,20.25,74.05,19.85',
        bounded: '0',

        q: `${trimmedQuery}, Nashik, Maharashtra, India`,
      })

      const response = await fetch(
        `https://nominatim.openstreetmap.org/search?${params.toString()}`,
        {
          headers: {
            Accept: 'application/json',
          },
        },
      )

      if (!response.ok) {
        throw new Error('Search request failed.')
      }

      const results = await response.json()

      if (requestId !== searchRequestRef.current) {
        return
      }

      const nashikResults = results.filter((result) => {
        const latitude = Number(result.lat)
        const longitude = Number(result.lon)

        if (!isInsideNashik(latitude, longitude)) {
          return false
        }

        const address = result.address || {}
        const displayName = (
          result.display_name || ''
        ).toLowerCase()

        const mentionsNashik =
          displayName.includes('nashik') ||
          address.city?.toLowerCase() === 'nashik' ||
          address.town?.toLowerCase() === 'nashik' ||
          address.city_district?.toLowerCase() === 'nashik'

        const mentionsMaharashtra =
          displayName.includes('maharashtra') ||
          address.state?.toLowerCase() === 'maharashtra'

        return mentionsNashik && mentionsMaharashtra
      })

      setSearchResults(nashikResults)
      setShowSuggestions(true)

      if (!nashikResults.length) {
        setSearchError('No matching Nashik location found.')
      }
    } catch {
      if (requestId === searchRequestRef.current) {
        setSearchResults([])

        setSearchError(
          'Unable to search right now. You can select the location directly on the map.',
        )
      }
    } finally {
      if (requestId === searchRequestRef.current) {
        setSearching(false)
      }
    }
  }

  /*
   * Debounced autocomplete.
   */
  useEffect(() => {
    const query = searchQuery.trim()

    if (searchTimeoutRef.current) {
      clearTimeout(searchTimeoutRef.current)
    }

    if (query.length < 2) return undefined

    searchTimeoutRef.current = setTimeout(() => {
      fetchSuggestions(query)
    }, 450)

    return () => {
      if (searchTimeoutRef.current) {
        clearTimeout(searchTimeoutRef.current)
      }
    }
  }, [searchQuery])

  const handleSearchQueryChange = (value) => {
    setSearchQuery(value)

    if (value.trim().length < 2) {
      setSearchResults([])
      setSearching(false)
      setSearchError('')
      setShowSuggestions(false)
    }
  }

  /*
   * Select autocomplete result.
   */
  const selectSearchResult = (result) => {
    const latitude = Number(result.lat)
    const longitude = Number(result.lon)

    if (
      !Number.isFinite(latitude) ||
      !Number.isFinite(longitude)
    ) {
      return
    }

    if (!isInsideNashik(latitude, longitude)) {
      setSearchError(
        'That result is outside the Nashik area.',
      )
      return
    }

    selectLocation(latitude, longitude)

    setSearchQuery(
      result.display_name
        ?.split(',')
        .slice(0, 3)
        .join(', ')
        .trim() || '',
    )

    setSearchResults([])
    setShowSuggestions(false)
    setSearchError('')
  }

  const searchLocation = async (event) => {
    event.preventDefault()

    const query = searchQuery.trim()

    if (!query) {
      setSearchError('Enter a Nashik location to search.')
      return
    }

    setShowSuggestions(false)

    await fetchSuggestions(query)
  }

  /*
   * Confirm location.
   */
  const confirmLocation = () => {
    if (!selectedPosition) {
      return
    }

    setConfirmed(true)

    onLocationSelect?.({
      latitude: selectedPosition[0],
      longitude: selectedPosition[1],
      address: selectedAddress,
      pincode: selectedPincode,
      confirmed: true,
    })
  }

  /*
   * Reset everything.
   */
  const resetLocation = () => {
    setSelectedPosition(null)
    setConfirmed(false)

    setSearchQuery('')
    setSearchResults([])

    setSelectedAddress('')
    setSelectedPincode('')

    setSearchError('')
    setLocationError('')

    setShowSuggestions(false)

    onLocationSelect?.(null)
  }

  return (
    <div
      style={{
        width: '100%',
      }}
    >
      {/* Header */}
      <div
        style={{
          marginBottom: '12px',
        }}
      >
        <strong>Complaint location</strong>

        <div
          style={{
            fontSize: '14px',
            marginTop: '4px',
            color: '#555',
          }}
        >
          Search a Nashik area or landmark, use your location,
          or click/drag the marker.
        </div>
      </div>

      {/* Search */}
      <form
        onSubmit={searchLocation}
        style={{
          position: 'relative',
          display: 'flex',
          gap: '8px',
          marginBottom: '10px',
          width: '100%',
        }}
      >
        <div
          style={{
            position: 'relative',
            flex: 1,
            minWidth: 0,
          }}
        >
          <input
            type="search"
            value={searchQuery}
            onChange={(event) => {
              handleSearchQueryChange(event.target.value)
              setShowSuggestions(true)
            }}
            onFocus={() => {
              if (searchResults.length) {
                setShowSuggestions(true)
              }
            }}
            onBlur={() => {
              setTimeout(() => {
                setShowSuggestions(false)
              }, 180)
            }}
            placeholder="🔍 Search Nashik area, road or landmark..."
            autoComplete="off"
            style={{
              width: '100%',
              boxSizing: 'border-box',
              padding: '11px 12px',
              borderRadius: '8px',
              border: '1px solid #ccc',
              fontSize: '14px',
              outline: 'none',
            }}
          />

          {/* Autocomplete */}
          {showSuggestions &&
            searchQuery.trim().length >= 2 &&
            (searching || searchResults.length > 0) && (
              <div
                style={{
                  position: 'absolute',
                  top: 'calc(100% + 4px)',
                  left: 0,
                  right: 0,
                  zIndex: 2000,
                  background: '#fff',
                  border: '1px solid #ddd',
                  borderRadius: '10px',
                  boxShadow:
                    '0 8px 20px rgba(0,0,0,0.12)',
                  overflow: 'hidden',
                  maxHeight: '300px',
                  overflowY: 'auto',
                }}
              >
                {searching && (
                  <div
                    style={{
                      padding: '12px 14px',
                      fontSize: '14px',
                      color: '#666',
                    }}
                  >
                    🔎 Searching Nashik locations...
                  </div>
                )}

                {!searching &&
                  searchResults.map((result) => (
                    <button
                      key={`${result.place_id}-${result.lat}-${result.lon}`}
                      type="button"
                      onMouseDown={(event) => {
                        event.preventDefault()
                      }}
                      onClick={() =>
                        selectSearchResult(result)
                      }
                      style={{
                        width: '100%',
                        padding: '11px 14px',
                        border: 'none',
                        borderBottom: '1px solid #eee',
                        background: '#fff',
                        textAlign: 'left',
                        cursor: 'pointer',
                      }}
                    >
                      <div
                        style={{
                          fontWeight: 600,
                          fontSize: '14px',
                          color: '#222',
                        }}
                      >
                        📍{' '}
                        {result.display_name
                          ?.split(',')
                          .slice(0, 2)
                          .join(', ')}
                      </div>

                      <div
                        style={{
                          marginTop: '3px',
                          fontSize: '12px',
                          color: '#777',
                        }}
                      >
                        {result.display_name
                          ?.split(',')
                          .slice(2, 5)
                          .join(', ')
                          .trim()}
                      </div>
                    </button>
                  ))}
              </div>
            )}
        </div>

        <button
          type="submit"
          disabled={searching}
          style={{
            padding: '10px 16px',
            borderRadius: '8px',
            border: 'none',
            background: '#2563eb',
            color: '#fff',
            cursor: searching ? 'wait' : 'pointer',
            whiteSpace: 'nowrap',
          }}
        >
          {searching ? 'Searching...' : 'Search'}
        </button>
      </form>

      {/* Current location */}
      <button
        type="button"
        onClick={() => detectLocation()}
        disabled={loadingLocation}
        style={{
          width: '100%',
          padding: '11px 16px',
          marginBottom: '10px',
          borderRadius: '8px',
          border: '1px solid #ccc',
          background: '#fff',
          cursor: loadingLocation ? 'wait' : 'pointer',
          fontSize: '14px',
        }}
      >
        {loadingLocation
          ? '⏳ Detecting your location...'
          : '📍 Use my current location'}
      </button>

      {/* Errors */}
      {(locationError || searchError) && (
        <div
          role="alert"
          style={{
            marginBottom: '10px',
            padding: '10px 12px',
            borderRadius: '8px',
            background: '#fff3cd',
            color: '#664d03',
            fontSize: '14px',
          }}
        >
          {locationError || searchError}
        </div>
      )}

      {/* Map */}
      <div
        style={{
          position: 'relative',
          width: '100%',
          height: 'min(55vh, 480px)',
          minHeight: '320px',
        }}
      >
        <MapContainer
          center={initialPosition}
          zoom={zoom}
          scrollWheelZoom
          style={{
            width: '100%',
            height: '100%',
            borderRadius: '12px',
          }}
        >
          <TileLayer
            attribution="&copy; OpenStreetMap contributors"
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />

          <MapRecenter position={selectedPosition} />

          <LocationMarker
            position={selectedPosition}
            icon={customIcon}
            onLocationSelect={(location) => {
              selectLocation(
                location.latitude,
                location.longitude,
              )
            }}
          />

          <LocateMeButton
            onLocate={detectLocation}
            loading={loadingLocation}
          />
        </MapContainer>
      </div>

      {/* Selected location card */}
      {selectedPosition && (
        <div
          style={{
            marginTop: '10px',
            padding: '14px',
            borderRadius: '10px',
            border: '1px solid #ddd',
            background: confirmed
              ? '#f0fdf4'
              : '#f8fafc',
          }}
        >
          <div
            style={{
              fontWeight: 600,
              marginBottom: '8px',
            }}
          >
            {confirmed
              ? '✓ Location confirmed'
              : '📍 Location selected'}
          </div>

          {/* Address */}
          <div
            style={{
              fontSize: '13px',
              color: '#444',
              marginBottom: '8px',
              wordBreak: 'break-word',
            }}
          >
            {loadingAddress ? (
              '🔎 Finding address...'
            ) : selectedAddress ? (
              <>
                <div
                  style={{
                    fontWeight: 500,
                    color: '#222',
                    marginBottom: '6px',
                  }}
                >
                  {selectedAddress}
                </div>

                {selectedPincode && (
                  <div
                    style={{
                      marginBottom: '6px',
                    }}
                  >
                    <strong>PIN:</strong>{' '}
                    {selectedPincode}
                  </div>
                )}

                {!selectedPincode && (
                  <div
                    style={{
                      fontSize: '12px',
                      color: '#888',
                      marginBottom: '6px',
                    }}
                  >
                    PIN code unavailable for this exact
                    location.
                  </div>
                )}
              </>
            ) : (
              <div
                style={{
                  color: '#777',
                }}
              >
                Address could not be determined. Coordinates
                are still available.
              </div>
            )}

            {/* Coordinates */}
            <div
              style={{
                fontSize: '12px',
                color: '#777',
              }}
            >
              Coordinates:{' '}
              {selectedPosition[0].toFixed(6)},{' '}
              {selectedPosition[1].toFixed(6)}
            </div>
          </div>

          {/* Buttons */}
          <div
            style={{
              display: 'flex',
              gap: '8px',
              flexWrap: 'wrap',
            }}
          >
            {!confirmed && (
              <button
                type="button"
                onClick={confirmLocation}
                style={{
                  padding: '9px 14px',
                  borderRadius: '7px',
                  border: 'none',
                  background: '#16a34a',
                  color: '#fff',
                  cursor: 'pointer',
                }}
              >
                ✓ Confirm Location
              </button>
            )}

            <button
              type="button"
              onClick={resetLocation}
              style={{
                padding: '9px 14px',
                borderRadius: '7px',
                border: '1px solid #ccc',
                background: '#fff',
                cursor: 'pointer',
              }}
            >
              ↺ Reset
            </button>
          </div>
        </div>
      )}

      <div
        style={{
          marginTop: '8px',
          fontSize: '12px',
          color: '#777',
        }}
      >
        Tip: Drag the marker to fine-tune the exact complaint
        location.
      </div>

      <div
        style={{
          marginTop: '4px',
          fontSize: '11px',
          color: '#999',
        }}
      >
        Address information is provided by OpenStreetMap
        geocoding. The selected coordinates are the exact
        location.
      </div>
    </div>
  )
}

export default MapPicker
