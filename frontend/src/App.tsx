import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom"

import { HomePage } from "./pages/HomePage"
import { PlanPage } from "./pages/PlanPage"
import { PoolPage } from "./pages/PoolPage"
import "./styles/globals.css"

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<HomePage />} path="/" />
        <Route element={<PoolPage />} path="/pool" />
        <Route element={<PlanPage />} path="/plan" />
        <Route element={<Navigate replace to="/" />} path="*" />
      </Routes>
    </BrowserRouter>
  )
}
