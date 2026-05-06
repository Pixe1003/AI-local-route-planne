import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom"

import { PlanResultPage } from "./pages/PlanResultPage"
import { RecommendPoolPage } from "./pages/RecommendPoolPage"
import { TripCreatePage } from "./pages/TripCreatePage"
import { TripDetailPage } from "./pages/TripDetailPage"
import { TripHomePage } from "./pages/TripHomePage"
import "./styles/globals.css"

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<TripHomePage />} path="/" />
        <Route element={<TripCreatePage />} path="/trips/new" />
        <Route element={<RecommendPoolPage />} path="/trips/new/pool" />
        <Route element={<TripDetailPage />} path="/trips/:tripId" />
        <Route element={<PlanResultPage />} path="/trips/:tripId/plan" />
        <Route element={<Navigate replace to="/trips/new/pool" />} path="/pool" />
        <Route element={<PlanResultPage />} path="/plan" />
        <Route element={<Navigate replace to="/" />} path="*" />
      </Routes>
    </BrowserRouter>
  )
}
