import { useEffect, useRef } from 'react';

/**
 * Infinite scroll con IntersectionObserver (roadmap #9).
 *
 * Observa el elemento `sentinelRef`; cuando entra en el viewport
 * (con margen de 400px) llama a `loadMore`. Si tras cargar el sentinel
 * sigue visible (página pequeña), el efecto se re-ejecuta (cambia
 * `loading` / `loadMore`) y carga otra página hasta llenar la pantalla.
 *
 * PROTECCIÓN: la página que usa este hook debe guardar la carga en vuelo
 * con un ref (inflightRef) dentro de `loadMore`, porque el observer puede
 * disparar dos veces antes del re-render.
 *
 * @param {Object} opts
 * @param {boolean} opts.hasMore   - Si quedan elementos por cargar
 * @param {boolean} opts.loading   - Si hay una petición en vuelo
 * @param {Function} opts.loadMore - Función (useCallback) que carga la siguiente página
 * @returns {Ref} sentinelRef      - Colócalo en un div al final del grid
 */
const useInfiniteScroll = ({ hasMore, loading, loadMore }) => {
  const sentinelRef = useRef(null);

  useEffect(() => {
    const el = sentinelRef.current;
    if (!el || !hasMore || loading) return undefined;

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting && !loading) {
          loadMore();
        }
      },
      { rootMargin: '400px 0px' }
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, [hasMore, loading, loadMore]);

  return sentinelRef;
};

export default useInfiniteScroll;
