/* Service Worker — Menu Familial */
/* Servi depuis / pour que le scope couvre toute l'application. */

const CACHE_VERSION = 'v1';
const CACHE_STATIC  = `menu-static-${CACHE_VERSION}`;
const CACHE_PAGES   = `menu-pages-${CACHE_VERSION}`;

/* Assets statiques pré-cachés à l'installation */
const PRECACHE_ASSETS = [
    '/static/menu/css/main.css',
    '/static/menu/js/planning.js',
    '/static/menu/js/courses.js',
    '/static/menu/js/recette_form.js',
    '/static/menu/manifest.json',
    '/static/menu/icons/icon-192.png',
    '/static/menu/icons/icon-512.png',
];

/* ── Installation ─────────────────────────────────────────────── */
self.addEventListener('install', event => {
    event.waitUntil(
        caches.open(CACHE_STATIC)
            .then(cache => cache.addAll(PRECACHE_ASSETS))
            .then(() => self.skipWaiting())
    );
});

/* ── Activation — purge des anciens caches ──────────────────── */
self.addEventListener('activate', event => {
    const KNOWN = [CACHE_STATIC, CACHE_PAGES];
    event.waitUntil(
        caches.keys()
            .then(keys => Promise.all(
                keys.filter(k => !KNOWN.includes(k)).map(k => caches.delete(k))
            ))
            .then(() => self.clients.claim())
    );
});

/* ── Fetch ──────────────────────────────────────────────────── */
self.addEventListener('fetch', event => {
    const req = event.request;
    const url = new URL(req.url);

    /* Ignorer les requêtes non-GET et cross-origin */
    if (req.method !== 'GET' || url.origin !== self.location.origin) return;

    /* Assets statiques → Cache-first (ils sont versionnés par WhiteNoise) */
    if (url.pathname.startsWith('/static/')) {
        event.respondWith(cacheFirst(req, CACHE_STATIC));
        return;
    }

    /* Fiches recettes → Network-first avec fallback cache (lecture hors-ligne) */
    if (url.pathname.startsWith('/recettes/') && !url.pathname.includes('/modifier/')
        && !url.pathname.includes('/supprimer/') && !url.pathname.includes('/creer')) {
        event.respondWith(networkFirst(req, CACHE_PAGES));
        return;
    }

    /* Tout le reste → Network only (planning, courses, API…) */
    /* On ne cache pas les pages dynamiques sensibles */
});

/* ── Stratégies ─────────────────────────────────────────────── */

async function cacheFirst(req, cacheName) {
    const cached = await caches.match(req);
    if (cached) return cached;
    try {
        const resp = await fetch(req);
        if (resp.ok) {
            const cache = await caches.open(cacheName);
            cache.put(req, resp.clone());
        }
        return resp;
    } catch {
        return new Response('Ressource indisponible hors-ligne.', { status: 503 });
    }
}

async function networkFirst(req, cacheName) {
    try {
        const resp = await fetch(req);
        if (resp.ok) {
            const cache = await caches.open(cacheName);
            cache.put(req, resp.clone());
        }
        return resp;
    } catch {
        const cached = await caches.match(req);
        if (cached) return cached;
        return new Response(
            '<!doctype html><html lang="fr"><body style="font-family:sans-serif;padding:2rem">'
            + '<h1>📵 Hors-ligne</h1><p>Cette page n\'est pas disponible sans connexion.</p>'
            + '<a href="/planning/">← Retour au planning</a></body></html>',
            { status: 503, headers: { 'Content-Type': 'text/html; charset=utf-8' } }
        );
    }
}
