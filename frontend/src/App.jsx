import { NavLink, Route, Routes } from "react-router-dom";
import HomePage from "./pages/HomePage.jsx";
import ProjectsPage from "./pages/ProjectsPage.jsx";
import ProjectPage from "./pages/ProjectPage.jsx";
import OutlinesPage from "./pages/OutlinesPage.jsx";
import OutlinePage from "./pages/OutlinePage.jsx";
import ReviewPage from "./pages/ReviewPage.jsx";
import SettingsPage from "./pages/SettingsPage.jsx";

export default function App() {
  return (
    <div className="app">
      <header className="topbar">
        <NavLink to="/" className="brand">
          <span aria-hidden>🪶</span> RavenQuill
        </NavLink>
        <nav>
          <NavLink to="/" end>
            Home
          </NavLink>
          <NavLink to="/projects">Projects</NavLink>
          <NavLink to="/outlines">Outlines</NavLink>
          <NavLink to="/settings">Settings</NavLink>
        </nav>
        <span className="private-badge" title="All editing runs on your own computer through LM Studio">
          Local &amp; private
        </span>
      </header>
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/projects" element={<ProjectsPage />} />
        <Route path="/projects/:id" element={<ProjectPage />} />
        <Route path="/projects/:id/review" element={<ReviewPage />} />
        <Route path="/outlines" element={<OutlinesPage />} />
        <Route path="/outlines/:id" element={<OutlinePage />} />
        <Route path="/settings" element={<SettingsPage />} />
      </Routes>
    </div>
  );
}
