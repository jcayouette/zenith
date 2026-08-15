import { NavLink, Route, Routes } from "react-router-dom";
import Archive from "./pages/Archive";
import Live from "./pages/Live";
import Processed from "./pages/Processed";
import Settings from "./pages/Settings";
import System from "./pages/System";
import Placeholder from "./pages/Placeholder";

const links = [
  { to: "/", label: "Live" },
  { to: "/archive", label: "Archive" },
  { to: "/processed", label: "Processed" },
  { to: "/charts", label: "Charts" },
  { to: "/sky", label: "Sky" },
  { to: "/detections", label: "Detections" },
  { to: "/settings", label: "Settings" },
  { to: "/system", label: "System" },
];

export default function App() {
  return (
    <div className="sky-bg min-h-screen">
      <header className="sticky top-0 z-20 border-b border-white/8 bg-[#070b14]/80 backdrop-blur-md">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-6 px-6 py-4">
          <div className="flex items-baseline gap-3">
            <span className="display text-2xl text-ice">Zenith</span>
            <span className="text-[11px] uppercase tracking-[0.28em] text-white/45">all-sky</span>
          </div>
          <nav className="flex flex-wrap gap-1">
            {links.map((link) => (
              <NavLink
                key={link.to}
                to={link.to}
                end={link.to === "/"}
                className={({ isActive }) =>
                  `rounded-full px-3 py-1.5 text-sm transition ${
                    isActive
                      ? "bg-white/10 text-ice"
                      : "text-white/55 hover:bg-white/5 hover:text-white"
                  }`
                }
              >
                {link.label}
              </NavLink>
            ))}
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-7xl px-6 py-8">
        <Routes>
          <Route path="/" element={<Live />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="/archive" element={<Archive />} />
          <Route path="/archive/:kind/:date" element={<Archive />} />
          <Route path="/processed" element={<Processed />} />
          <Route
            path="/charts"
            element={<Placeholder title="Charts" note="Exposure, ADU, star count, SQM, Kp, and sensors." />}
          />
          <Route
            path="/sky"
            element={<Placeholder title="Sky" note="Named satellites, ISS passes, Stellarium import." />}
          />
          <Route
            path="/detections"
            element={<Placeholder title="Detections" note="Meteors, aircraft, and highlight reels." />}
          />
          <Route
            path="/system"
            element={<System />}
          />
        </Routes>
      </main>
    </div>
  );
}
