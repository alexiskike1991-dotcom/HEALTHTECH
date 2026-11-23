// HealthTech TACO - modo sin internet:
//  1) la pagina abre aunque no haya conexion (service worker, solo en el navegador),
//  2) muestra la ultima informacion guardada (solo lectura),
//  3) si se escanea una receta sin internet, la foto queda en espera y se lee sola cuando vuelve la conexion.
(function () {
  'use strict';
  const g = id => document.getElementById(id);
  const esApp = !!(window.Capacitor && window.Capacitor.isNativePlatform && window.Capacitor.isNativePlatform());

  // ---------- 1) Pagina disponible sin internet (navegador) ----------
  if (!esApp && 'serviceWorker' in navigator && /^https?:$/.test(location.protocol)) {
    window.addEventListener('load', () => navigator.serviceWorker.register('sw.js').catch(() => {}));
  }

  // ---------- Almacen local ----------
  let dbP = null;
  function db() {
    if (dbP) return dbP;
    dbP = new Promise((ok, mal) => {
      try {
        const r = indexedDB.open('healthtech_offline', 1);
        r.onupgradeneeded = () => {
          r.result.createObjectStore('cache', { keyPath: 'key' });
          r.result.createObjectStore('pendientes', { keyPath: 'id', autoIncrement: true });
        };
        r.onsuccess = () => ok(r.result);
        r.onerror = () => mal(r.error);
      } catch (e) { mal(e); }
    });
    return dbP;
  }
  async function op(tabla, modo, fn) {
    const d = await db();
    return new Promise((ok, mal) => {
      const t = d.transaction(tabla, modo); let req;
      try { req = fn(t.objectStore(tabla)); } catch (e) { mal(e); return; }
      t.oncomplete = () => ok(req && req.result);
      t.onerror = () => mal(t.error);
    });
  }
  const uid = () => localStorage.getItem('taco_id') || '';

  // ---------- 2) Ultima informacion guardada ----------
  const sinConexion = e => !!e && /No se pudo conectar/i.test(e.message || '');
  let offline = false;
  function aviso(on) {
    offline = on;
    let b = g('avisoSinInternet');
    if (!b) {
      b = document.createElement('div');
      b.id = 'avisoSinInternet';
      b.setAttribute('role', 'status');
      b.style.cssText = 'display:none;position:fixed;top:0;left:0;right:0;z-index:2600;background:#B45309;color:#fff;text-align:center;padding:8px 12px;font:600 13px system-ui,sans-serif';
      b.textContent = 'Sin internet: estás viendo tu última información guardada. Los cambios se podrán hacer cuando vuelva la conexión.';
      document.body.append(b);
    }
    b.style.display = on ? 'block' : 'none';
    pintarPendientes();
  }

  window.__fetchAPIHook = async function (base, path, options, reintento) {
    const metodo = String((options && options.method) || 'GET').toUpperCase();
    try {
      const res = await base(path, options, reintento);
      if (offline) aviso(false);
      if (metodo === 'GET' && uid()) op('cache', 'readwrite', s => s.put({ key: `${uid()}:${path}`, res })).catch(() => {});
      return res;
    } catch (e) {
      if (sinConexion(e)) {
        if (metodo === 'GET' && uid()) {
          const c = await op('cache', 'readonly', s => s.get(`${uid()}:${path}`)).catch(() => null);
          if (c && c.res) { aviso(true); return c.res; }
        }
        aviso(true);
      }
      throw e;
    }
  };

  // Al cerrar sesion se borra lo guardado de ese usuario (otra persona podria usar el equipo).
  async function borrarDeUsuario(u) {
    if (!u) return;
    const todo = await op('cache', 'readonly', s => s.getAll()).catch(() => []);
    for (const r of todo || []) if (r.key.startsWith(`${u}:`)) await op('cache', 'readwrite', s => s.delete(r.key)).catch(() => {});
    const pend = await op('pendientes', 'readonly', s => s.getAll()).catch(() => []);
    for (const p of pend || []) if (p.uid === u) await op('pendientes', 'readwrite', s => s.delete(p.id)).catch(() => {});
  }
  ['btnSalir', 'btnSalirStaff'].forEach(id => g(id)?.addEventListener('click', () => { borrarDeUsuario(uid()); }, true));

  // ---------- 3) Fotos de recetas en espera ----------
  let procesando = null;   // id de la foto que se esta leyendo ahora
  async function listaPendientes() {
    const t = await op('pendientes', 'readonly', s => s.getAll()).catch(() => []);
    return (t || []).filter(p => p.uid === uid());
  }
  window.encolarReceta = async function (archivo) {
    if (procesando) return;   // ya hay una en espera: no se duplica
    await op('pendientes', 'readwrite', s => s.add({ uid: uid(), archivo, nombre: archivo.name || 'receta.jpg', fecha: Date.now() }));
    await pintarPendientes();
  };

  document.addEventListener('submit', async e => {
    if (!e.target || e.target.id !== 'formReceta' || navigator.onLine) return;
    const archivo = g('inputImagen')?.files?.[0];
    e.preventDefault(); e.stopImmediatePropagation();
    const msg = g('mensajeReceta');
    if (!archivo) { if (msg) msg.textContent = 'Selecciona una imagen primero.'; return; }
    await window.encolarReceta(archivo);
    if (g('inputImagen')) g('inputImagen').value = '';
    if (msg) msg.textContent = 'Sin internet: guardé la foto de tu receta. Se leerá sola cuando vuelva la conexión.';
  }, true);

  const tarjeta = document.createElement('div');
  tarjeta.id = 'recetasEnEspera';
  tarjeta.style.cssText = 'display:none;position:fixed;left:12px;right:12px;bottom:84px;z-index:2400;background:#fff;border:2px solid #0C8F68;border-radius:14px;padding:12px 14px;box-shadow:0 8px 24px rgba(0,0,0,.2);font:14px system-ui,sans-serif;color:#073B30';
  document.body.append(tarjeta);
  async function pintarPendientes() {
    const p = await listaPendientes();
    if (!p.length) { tarjeta.style.display = 'none'; return; }
    const hayRed = navigator.onLine && !offline;
    tarjeta.innerHTML = `<strong>${p.length} receta(s) esperando</strong><br>` +
      (hayRed ? 'Ya hay internet. Toca el botón para leerla con la IA.' : 'Esperando internet. Tu foto está guardada en este equipo.') +
      (hayRed ? '<br><button type="button" id="btnLeerEspera" class="btn-primary" style="margin-top:8px">Leer ahora</button>' : '');
    tarjeta.style.display = 'block';
    g('btnLeerEspera')?.addEventListener('click', procesarEspera);
  }
  async function procesarEspera() {
    if (procesando || !accessToken) return;
    const p = (await listaPendientes())[0];
    if (!p) return;
    procesando = p.id;
    const input = g('inputImagen'), form = g('formReceta');
    if (!input || !form) { procesando = null; return; }
    const dt = new DataTransfer(); dt.items.add(new File([p.archivo], p.nombre, { type: p.archivo.type || 'image/jpeg' }));
    input.files = dt.files;
    tarjeta.style.display = 'none';
    form.requestSubmit();
  }
  // app.js avisa cuando termina de procesar una receta: ok / cancelado / error
  document.addEventListener('receta-procesada', async e => {
    const estado = e.detail && e.detail.estado;
    if (procesando && (estado === 'ok' || estado === 'cancelado')) await op('pendientes', 'readwrite', s => s.delete(procesando)).catch(() => {});
    procesando = null;
    pintarPendientes();
    if (estado === 'ok' && (await listaPendientes()).length) pintarPendientes();
  });

  async function alVolverInternet() {
    aviso(false);
    try { if (typeof cargarMedicamentos === 'function') await cargarMedicamentos(); if (typeof cargarHistorial === 'function') await cargarHistorial(); } catch (e) {}
    pintarPendientes();
  }
  window.addEventListener('online', alVolverInternet);
  window.addEventListener('offline', () => aviso(true));
  setInterval(pintarPendientes, 5000);
  if (!navigator.onLine) aviso(true); else pintarPendientes();
})();
