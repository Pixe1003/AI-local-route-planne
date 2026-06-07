import { Activity, ChevronDown, Compass, Heart, Map, Route, Sparkles } from "lucide-react"
import { NavLink, Outlet } from "react-router-dom"

const navItems = [
  { to: "/", label: "路线工作台", icon: Compass },
  { to: "/favorites", label: "收藏偏好", icon: Heart },
  { to: "/route-map", label: "高德路线", icon: Route }
]

export function AppLayout() {
  return (
    <div className="app-layout">
      <header className="app-topbar">
        <div className="app-brand-lockup" aria-label="AIroute">
          <span className="side-nav-brand app-brand-mark">
            <Map size={20} />
          </span>
          <div>
            <strong>AIroute</strong>
            <small>本地生活路线 Agent</small>
          </div>
        </div>

        <nav className="side-nav app-nav" aria-label="主导航">
          <div className="side-nav-links app-nav-links">
            {navItems.map(item => {
              const Icon = item.icon
              return (
                <NavLink
                  className={({ isActive }) => (isActive ? "side-nav-link active" : "side-nav-link")}
                  end={item.to === "/"}
                  key={item.to}
                  title={item.label}
                  to={item.to}
                >
                  <Icon size={17} />
                  <span>{item.label}</span>
                </NavLink>
              )
            })}
          </div>
        </nav>

        <div className="app-topbar-status" aria-label="服务状态">
          <span className="service-chip healthy">
            <Activity size={14} />
            系统正常
          </span>
          <span className="service-chip">Agent 运行中</span>
          <button className="topbar-primary-action" type="button">
            <Sparkles size={16} />
            生成路线
          </button>
          <button className="topbar-account" type="button" aria-label="账户菜单">
            A
            <ChevronDown size={14} />
          </button>
        </div>
      </header>

      <Outlet />
    </div>
  )
}
