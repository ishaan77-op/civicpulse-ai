import { useEffect, useState } from 'react'
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

function MapRecenter({ position }) {
  const map = useMap()

  useEffect(() => {
    if (position) {
      map.flyTo(position, 15, {
        duration: 1,
      })
    }
  }, [map, position])

  return null
}

function LocationMarker({ position, onLocationSelect }) {
  useMapEvents({
    click(event) {
      const location = {
        latitude: event.latlng.lat,
        longitude: event.latlng.lng,
      }

      onLocationSelect?.(location)
    },
  })

  return position ? <Marker position={position} /> : null
}

function MapPicker({
  onLocationSelect,
  initialPosition = NASHIK_CENTER,
  zoom = 12,
}) {
  const [selectedPosition, setSelectedPosition] = useState(null)
  const [loadingLocation, setLoadingLocation] = useState(false)
  const [locationError, setLocationError] = useState('')

  const selectLocation = (latitude, longitude) => {
    const position = [latitude, longitude]

    const location = {
      latitude,
      longitude,
    }

    setSelectedPosition(position)
    onLocationSelect?.(location)
  }

  const detectLocation = () => {
    if (!navigator.geolocation) {
      setLocationError('Location detection is not supported by your browser.')
      return
    }

    setLoadingLocation(true)
    setLocationError('')

    navigator.geolocation.getCurrentPosition(
      (position) => {
        const { latitude, longitude } = position.coords

        selectLocation(latitude, longitude)
        setLoadingLocation(false)
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

  return (
    <div style={{ width: '100%' }}>
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          gap: '12px',
          marginBottom: '12px',
          flexWrap: 'wrap',
        }}
      >
        <div>
          <strong>Complaint location</strong>

          <div style={{ fontSize: '14px', marginTop: '4px' }}>
            Use your current location or click anywhere on the map.
          </div>
        </div>

        <button
          type="button"
          onClick={detectLocation}
          disabled={loadingLocation}
          style={{
            padding: '10px 16px',
            borderRadius: '8px',
            border: '1px solid #ccc',
            background: '#fff',
            cursor: loadingLocation ? 'wait' : 'pointer',
          }}
        >
          {loadingLocation ? 'Detecting location...' : '📍 Use my location'}
        </button>
      </div>

      {locationError && (
        <div
          role="alert"
          style={{
            marginBottom: '12px',
            padding: '10px 12px',
            borderRadius: '8px',
            background: '#fff3cd',
            fontSize: '14px',
          }}
        >
          {locationError}
        </div>
      )}

      <MapContainer
        center={initialPosition}
        zoom={zoom}
        scrollWheelZoom
        style={{
          width: '100%',
          height: '400px',
          borderRadius: '12px',
        }}
      >
        <TileLayer
          attribution='&copy; OpenStreetMap contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />

        <MapRecenter position={selectedPosition} />

        <LocationMarker
          position={selectedPosition}
          onLocationSelect={(location) => {
            setSelectedPosition([
              location.latitude,
              location.longitude,
            ])

            onLocationSelect?.(location)
          }}
        />
      </MapContainer>

      {selectedPosition && (
        <div
          style={{
            marginTop: '10px',
            fontSize: '13px',
          }}
        >
          Selected location: {selectedPosition[0].toFixed(6)},{' '}
          {selectedPosition[1].toFixed(6)}
        </div>
      )}
    </div>
  )
}

export default MapPicker