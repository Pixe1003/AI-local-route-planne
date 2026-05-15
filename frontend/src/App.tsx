import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom"

import { AmapRoutePage } from "./pages/AmapRoutePage"
import { DiscoveryFeedPage } from "./pages/DiscoveryFeedPage"
import "./styles/globals.css"

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<DiscoveryFeedPage />} path="/" />
        <Route element={<AmapRoutePage />} path="/route-map" />
        <Route element={<Navigate replace to="/" />} path="*" />
      </Routes>
    </BrowserRouter>
  )
}
