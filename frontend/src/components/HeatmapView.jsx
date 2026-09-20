import { useEffect } from 'react'
import { MapContainer, TileLayer, useMap } from 'react-leaflet'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import 'leaflet.heat'

const NASHIK_CENTER = [20.0110, 73.7903]

function HeatLayer({ points }) {
  const map = useMap()

  useEffect(() => {
    const heatPoints = points.map((point) => [
      point.latitude,
      point.longitude,
      point.weight || 1,
    ])

    const heatLayer = L.heatLayer(heatPoints, {
      radius: 28,
      blur: 22,
      maxZoom: 17,
    }).addTo(map)

    return () => {
      map.removeLayer(heatLayer)
    }
  }, [map, points])

  return null
}

function HeatmapView({ points = [], height = 'min(60vh, 520px)' }) {
  return (
    <div style={{ width: '100%' }}>
      <div
        style={{
          position: 'relative',
          width: '100%',
          height,
          minHeight: '320px',
        }}
      >
        <MapContainer
          center={NASHIK_CENTER}
          zoom={12}
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

          <HeatLayer points={points} />
        </MapContainer>
      </div>

      {points.length === 0 && (
        <p className="page-state">
          No location data available yet for this filter.
        </p>
      )}
    </div>
  )
}

export default HeatmapView
