import { NavLink, Outlet } from 'react-router-dom';

export function Layout(): React.JSX.Element {
  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-[#1a1a2e] text-white shadow-md">
        <div className="max-w-6xl mx-auto px-6 py-4 flex items-center justify-between">
          <NavLink to="/" className="flex items-center gap-3 hover:opacity-90">
            <svg
              className="w-7 h-7 text-[#c8102e]"
              fill="currentColor"
              viewBox="0 0 24 24"
            >
              <path d="M4 4h16v16H4V4zm2 2v12h12V6H6zm2 2h8v2H8V8zm0 4h8v2H8v-2z" />
            </svg>
            <span className="text-lg font-semibold tracking-tight">
              Remotion Video Gen
            </span>
          </NavLink>

          <nav className="flex items-center gap-1">
            <NavLink
              to="/"
              end
              className={({ isActive }) =>
                `px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                  isActive
                    ? 'bg-white/15 text-white'
                    : 'text-gray-300 hover:text-white hover:bg-white/10'
                }`
              }
            >
              New
            </NavLink>
            <NavLink
              to="/history"
              className={({ isActive }) =>
                `px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                  isActive
                    ? 'bg-white/15 text-white'
                    : 'text-gray-300 hover:text-white hover:bg-white/10'
                }`
              }
            >
              History
            </NavLink>
            <NavLink
              to="/how-it-works"
              className={({ isActive }) =>
                `px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                  isActive
                    ? 'bg-white/15 text-white'
                    : 'text-gray-300 hover:text-white hover:bg-white/10'
                }`
              }
            >
              How it works
            </NavLink>
          </nav>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-6 py-8">
        <Outlet />
      </main>
    </div>
  );
}
