const CACHE_NAME = 'home-budget-v3';
const LOCAL_ASSETS = [
    './',
    './index.html',
    './app.js',
    './favicon.ico',
    './manifest.json',
    './icons/icon.svg',
];

self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME).then((cache) => cache.addAll(LOCAL_ASSETS))
    );
    self.skipWaiting();
});

self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys().then((keys) =>
            Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
        )
    );
    self.clients.claim();
});

self.addEventListener('fetch', (event) => {
    const url = new URL(event.request.url);
    const isExternal = url.hostname !== self.location.hostname;

    if (isExternal) {
        // Network-first for CDN: cache on success, fallback to cached if offline
        event.respondWith(
            fetch(event.request)
                .then((response) => {
                    const clone = response.clone();
                    caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
                    return response;
                })
                .catch(() => caches.match(event.request))
        );
    } else {
        // Cache-first for local assets
        event.respondWith(
            caches.match(event.request).then((response) => response || fetch(event.request))
        );
    }
});
