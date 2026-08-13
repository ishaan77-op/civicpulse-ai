import MapPicker from '../components/MapPicker.jsx'

function MapTest() {
  const handleLocationSelect = (location) => {
    console.log('Selected Nashik location:', location)
  }

  return (
    <div style={{ padding: '24px' }}>
      <h1>Nashik Complaint Location</h1>

      <p>
        Click on the map to select the location of your complaint.
      </p>

      <MapPicker
        onLocationSelect={handleLocationSelect}
        initialPosition={[20.0110, 73.7903]}
        zoom={12}
      />
    </div>
  )
}

export default MapTest