-- Migración: añadir ON DELETE CASCADE a las FK de download_queue
-- que referenciaban chapters y book_chapters sin cascade.
--
-- Ejecutar en producción:
--   docker compose exec -T postgres psql -U alejandria alejandria < scripts/migrate-fk-cascade.sql

BEGIN;

-- 1. Chapters (manga)
ALTER TABLE download_queue
    DROP CONSTRAINT IF EXISTS download_queue_chapter_id_fkey;
ALTER TABLE download_queue
    ADD CONSTRAINT download_queue_chapter_id_fkey
    FOREIGN KEY (chapter_id) REFERENCES chapters(id) ON DELETE CASCADE;

-- 2. Book chapters
ALTER TABLE download_queue
    DROP CONSTRAINT IF EXISTS download_queue_book_chapter_id_fkey;
ALTER TABLE download_queue
    ADD CONSTRAINT download_queue_book_chapter_id_fkey
    FOREIGN KEY (book_chapter_id) REFERENCES book_chapters(id) ON DELETE CASCADE;

-- comic_issue_id ya tiene ON DELETE CASCADE, no necesita cambio.

COMMIT;

SELECT 'Migración FK cascade completada.' AS resultado;
