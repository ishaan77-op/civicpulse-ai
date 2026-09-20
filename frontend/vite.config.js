import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const dirname = path.dirname(fileURLToPath(import.meta.url))

// Local HTTPS dev certificate (mkcert), needed so browser APIs that require a
// secure context (geolocation, camera) work when testing over the LAN IP.
// Generated via:
//   mkcert -key-file .cert/dev-key.pem -cert-file .cert/dev-cert.pem localhost 127.0.0.1 ::1 192.168.1.38
// Falls back to plain HTTP if the cert hasn't been generated on this machine.
const certPath = path.resolve(dirname, '.cert/dev-cert.pem')
const keyPath = path.resolve(dirname, '.cert/dev-key.pem')
const httpsOptions =
  fs.existsSync(certPath) && fs.existsSync(keyPath)
    ? { cert: fs.readFileSync(certPath), key: fs.readFileSync(keyPath) }
    : undefined

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    https: httpsOptions,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:5001',
        changeOrigin: true,
      },
      '/uploads': {
        target: 'http://127.0.0.1:5001',
        changeOrigin: true,
      },
    },
  },
})
