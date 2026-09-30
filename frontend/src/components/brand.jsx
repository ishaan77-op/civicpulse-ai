import { Link } from 'react-router-dom'
import logo from '../assets/nmc-smartfix-mark.png'

export default function Brand({ to = '/', className = '', compact = false }) {
  return (
    <Link className={`brand ${className}`.trim()} to={to} aria-label="NMC-SmartFix home">
      <img className="brand-logo" src={logo} alt="" />
      {!compact && <span className="brand-name">NMC-<em>SmartFix</em></span>}
    </Link>
  )
}
