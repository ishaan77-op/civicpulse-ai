import { BrowserRouter, Route, Routes } from 'react-router-dom'
import Home from './pages/home.jsx'
import Features from './pages/features.jsx'
import HowItWorks from './pages/how-it-works.jsx'
import About from './pages/about.jsx'
import Login from './pages/login.jsx'
import Register from './pages/register.jsx'

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/features" element={<Features />} />
        <Route path="/how-it-works" element={<HowItWorks />} />
        <Route path="/about" element={<About />} />
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
        <Route path="*" element={<Home />} />
      </Routes>
    </BrowserRouter>
  )
}

export default App
