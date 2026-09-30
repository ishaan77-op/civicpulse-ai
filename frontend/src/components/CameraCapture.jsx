import { useEffect, useRef, useState } from 'react'

function CameraCapture({ onCapture }) {
  const videoRef = useRef(null)
  const canvasRef = useRef(null)
  const streamRef = useRef(null)

  const [error, setError] = useState('')
  const [starting, setStarting] = useState(true)
  const [previewUrl, setPreviewUrl] = useState('')

  const stopStream = () => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop())
      streamRef.current = null
    }
  }

  const startCamera = async () => {
    setError('')
    setStarting(true)

    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      setStarting(false)
      setError(
        'Camera access is required to submit a report, and this browser does not support it. Please use an updated mobile browser.',
      )
      return
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: 'environment' },
        audio: false,
      })

      streamRef.current = stream

      if (videoRef.current) {
        videoRef.current.srcObject = stream
        await videoRef.current.play()
      }

      setStarting(false)
    } catch {
      setStarting(false)
      setError(
        'Camera access is required to submit a report. Please allow camera permissions and reload the page.',
      )
    }
  }

  useEffect(() => {
    const timer = window.setTimeout(startCamera, 0)
    return () => {
      window.clearTimeout(timer)
      stopStream()
    }
  }, [])

  const capturePhoto = () => {
    const video = videoRef.current
    const canvas = canvasRef.current

    if (!video || !canvas) return

    canvas.width = video.videoWidth
    canvas.height = video.videoHeight

    const context = canvas.getContext('2d')
    context.drawImage(video, 0, 0, canvas.width, canvas.height)

    canvas.toBlob(
      (blob) => {
        if (!blob) return

        const file = new File([blob], `report-${Date.now()}.jpg`, {
          type: 'image/jpeg',
        })

        setPreviewUrl(URL.createObjectURL(blob))
        stopStream()
        onCapture?.(file)
      },
      'image/jpeg',
      0.9,
    )
  }

  const retake = () => {
    if (previewUrl) URL.revokeObjectURL(previewUrl)
    setPreviewUrl('')
    onCapture?.(null)
    startCamera()
  }

  return (
    <div className="camera-capture">
      <canvas ref={canvasRef} style={{ display: 'none' }} />

      {error && (
        <p className="form-message error" role="alert">
          {error}
        </p>
      )}

      {!error && !previewUrl && (
        <div className="camera-preview-wrap">
          {starting && <p className="page-state">Starting camera…</p>}

          <video
            ref={videoRef}
            playsInline
            muted
            style={{
              width: '100%',
              maxHeight: '360px',
              borderRadius: '12px',
              background: '#000',
              objectFit: 'cover',
            }}
          />

          {!starting && (
            <button
              type="button"
              className="button button-primary"
              onClick={capturePhoto}
            >
              📷 Capture Photo
            </button>
          )}
        </div>
      )}

      {previewUrl && (
        <div className="camera-preview-wrap">
          <img
            src={previewUrl}
            alt="Captured issue"
            style={{
              width: '100%',
              maxHeight: '360px',
              borderRadius: '12px',
              objectFit: 'cover',
            }}
          />

          <button type="button" className="button" onClick={retake}>
            ↺ Retake
          </button>
        </div>
      )}
    </div>
  )
}

export default CameraCapture
