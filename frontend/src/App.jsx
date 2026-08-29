import { BrowserRouter, Route, Routes } from 'react-router-dom'
import Home from './pages/home.jsx'
import Features from './pages/features.jsx'
import HowItWorks from './pages/how-it-works.jsx'
import About from './pages/about.jsx'
import Login from './pages/login.jsx'
import Register from './pages/register.jsx'
import ProtectedRoute from './components/protectedroute.jsx'
import Dashboard from './pages/citizendashboard.jsx'
import Report from './pages/report.jsx'
import Complaints from './pages/complaints.jsx'
import ComplaintDetails from './pages/complaintdetails.jsx'
import Profile from './pages/profile.jsx'
import OfficerDashboard from './pages/officerdashboard.jsx'
import AdminDashboard from './pages/admindashboard.jsx'
import NotFound from './pages/notfound.jsx'

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
        <Route element={<ProtectedRoute />}>
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/report" element={<Report />} />
          <Route path="/complaints" element={<Complaints />} />
          <Route path="/complaints/:id" element={<ComplaintDetails />} />
          <Route path="/profile" element={<Profile />} />
          <Route element={<ProtectedRoute allowedRoles={['Officer', 'Admin']} />}>
            <Route path="/officer" element={<OfficerDashboard />} />
          </Route>
          <Route element={<ProtectedRoute allowedRoles={['Admin']} />}>
            <Route path="/admin" element={<AdminDashboard />} />
          </Route>
        </Route>
        <Route path="*" element={<NotFound />} />
      </Routes>
    </BrowserRouter>
  )
}

export default App
