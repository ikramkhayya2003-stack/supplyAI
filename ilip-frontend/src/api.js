export async function request(path, params = {}, signal) {
  const query = new URLSearchParams(Object.entries(params).filter(([,v]) => v !== '' && v != null));
  const response = await fetch(`/api${path}${query.size ? `?${query}` : ''}`, {signal: signal || AbortSignal.timeout(15000)});
  if (!response.ok) throw new Error(`API indisponible ou requête refusée (HTTP ${response.status}). Vérifie le terminal FastAPI et les filtres.`);
  const data = await response.json();
  return data;
}
