import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom"

import { AppLayout } from "./components/AppLayout"
import { AmapRoutePage } from "./pages/AmapRoutePage"
import { DiscoveryFeedPage } from "./pages/DiscoveryFeedPage"
import { FavoritesPage } from "./pages/FavoritesPage"
import { ProjectReviewPage } from "./pages/ProjectReviewPage"
import "./styles/globals.css"

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AppLayout />}>
          <Route element={<DiscoveryFeedPage />} path="/" />
          <Route element={<FavoritesPage />} path="/favorites" />
          <Route element={<AmapRoutePage />} path="/route-map" />
          <Route element={<ProjectReviewPage />} path="/review" />
        </Route>
        <Route element={<Navigate replace to="/" />} path="*" />
      </Routes>
    </BrowserRouter>
  )
}
