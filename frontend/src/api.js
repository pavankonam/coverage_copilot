// Single source of truth for the API base URL -- see .env.example.
// Vite only exposes env vars prefixed VITE_ to client code. Import this
// everywhere the base URL is needed instead of reading import.meta.env
// directly, so there's exactly one place it's wired up.
export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL
