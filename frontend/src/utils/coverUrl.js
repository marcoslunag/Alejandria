/**
 * Enruta portadas externas a través del proxy del backend (roadmap #12):
 * - Caché local del backend (un fetch por portada, TTL 7 días)
 * - ETag + Cache-Control en la respuesta
 * - Evita bloqueos de hotlink de los CDN
 *
 * Las URLs relativas/locales (subidas, OPDS local) pasan sin tocar.
 */
const API_BASE = import.meta.env.VITE_API_URL || '/api/v1';

export function proxyCover(url) {
  if (!url || typeof url !== 'string') return url;
  let parsed;
  try {
    parsed = new URL(url);
  } catch {
    return url; // relativa o no válida → la sirve el mismo origen
  }
  if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') return '#';
  return `${API_BASE}/covers/proxy?url=${encodeURIComponent(url)}`;
}
