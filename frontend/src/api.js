// Simple API utility for the React frontend
const API_BASE = import.meta.env.VITE_API_BASE_URL
  || (import.meta.env.DEV
    ? 'http://127.0.0.1:8000/api/inventory'
    : '/api/inventory');

export async function fetchProducts() {
  const res = await fetch(`${API_BASE}/products/`);
  if (!res.ok) throw new Error('Failed to fetch products');
  return res.json();
}

export async function fetchCategories() {
  const res = await fetch(`${API_BASE}/categories/`);
  if (!res.ok) throw new Error('Failed to fetch categories');
  return res.json();
}
