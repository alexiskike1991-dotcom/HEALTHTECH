// HealthTech TACO - Biblioteca de recetas con copia en el telefono (se ve aunque no haya internet).
(function () {
  'use strict';
  const g = id => document.getElementById(id);
  const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  // ---------- Copia local (IndexedDB) ----------
  let dbP = null;
  function db() {
    if (dbP) return dbP;
    dbP = new Promise((ok, mal) => {
      try {
        const r = indexedDB.open('healthtech_recetas', 1);
        r.onupgradeneeded = () => r.result.createObjectStore('recetas', { keyPath: 'key' });
        r.onsuccess = () => ok(r.result);
        r.onerror = () => mal(r.error);
      } catch (e) { mal(e); }
    });
    return dbP;
  }
  async function tx(modo, fn) {
    const d = await db();
    return new Promise((ok, mal) => {
      const t = d.transaction('recetas', modo), s = t.objectStore('recetas');
      let res; try { res = fn(s); } catch (e) { mal(e); return; }
      t.oncomplete = () => ok(res && res.result !== undefined ? res.result : res);
      t.onerror = () => mal(t.error);
    });
  }
  const todas = () => tx('readonly', s => s.getAll()).catch(() => []);
  const guardarLocal = reg => tx('readwrite', s => s.put(reg)).catch(() => {});
  const borrarLocal = key => tx('readwrite', s => s.delete(key)).catch(() => {});
  async function delUsuario(uid) { for (const r of await todas()) if (r.uid === String(uid)) await borrarLocal(r.key); }

  // ---------- Servidor ----------
  async function bajarImagen(id) {
    const res = await fetch(`${API}/recetas/${id}/imagen/`, { headers: { Authorization: `Bearer ${accessToken}` } });
    if (!res.ok) throw new Error('imagen');
    return res.blob();
  }
  let sincronizando = false;
  async function sincronizar() {
    if (sincronizando || !accessToken || !idUsuario) return false;
    sincronizando = true;
    const uid = String(idUsuario);
    try {
      const lista = await fetchAPI('/recetas/');
      const remotas = Array.isArray(lista.data) ? lista.data : [];
      const locales = (await todas()).filter(r => r.uid === uid);
      const tengo = new Set(locales.map(r => r.id));
      const vigentes = new Set(remotas.map(r => r.id));
      for (const l of locales) if (!vigentes.has(l.id)) await borrarLocal(l.key);
      for (const r of remotas) {
        if (tengo.has(r.id)) continue;
        try { await guardarLocal({ key: `${uid}:${r.id}`, uid, id: r.id, creada: r.creada, datos: r.datos || {}, blob: await bajarImagen(r.id) }); } catch (e) {}
      }
      return true;
    } catch (e) { return false; } finally { sincronizando = false; }
  }

  // ---------- Guardar una receta nueva (lo llama app.js al confirmar el escaneo) ----------
  window.guardarRecetaBiblioteca = async function (archivo, confirmado) {
    try {
      const f = new FormData();
      f.append('imagen', archivo);
      f.append('datos', JSON.stringify({
        medico: confirmado.medico, ultimoControl: confirmado.ultimoControl, proximoControl: confirmado.proximoControl,
        inr: confirmado.inr, min: confirmado.min, max: confirmado.max,
        medicamentos: (confirmado.medicamentos || []).map(m => m.nombre)
      }));
      await fetchAPI('/recetas/', { method: 'POST', body: f });
      await sincronizar();
      pintarSeccion();
    } catch (e) { console.warn('No se pudo guardar la receta en la biblioteca:', e); }
  };

  // ---------- Pantalla ----------
  const URLs = [];
  function fechaTxt(iso) { try { return new Date(iso).toLocaleDateString('es-CL', { day: '2-digit', month: 'long', year: 'numeric' }); } catch (e) { return ''; } }
  function tarjeta(r) {
    const url = URL.createObjectURL(r.blob); URLs.push(url);
    const d = r.datos || {};
    const detalle = [d.medico && `Médico: ${esc(d.medico)}`, d.inr != null && `INR: ${esc(d.inr)}`, d.proximoControl && `Próximo control: ${esc(d.proximoControl)}`,
      (d.medicamentos || []).length && esc(d.medicamentos.join(', '))].filter(Boolean).join('<br>');
    return `<article class="historial-item" style="display:flex;gap:12px;align-items:flex-start;margin-bottom:12px">
      <img src="${url}" alt="Receta" data-ver="${url}" style="width:84px;height:112px;object-fit:cover;border-radius:10px;border:1px solid #DCE7E2;cursor:pointer">
      <div style="flex:1;min-width:0"><strong>${esc(fechaTxt(r.creada))}</strong><p class="muted" style="margin:6px 0">${detalle || 'Sin datos leídos'}</p>
      <button type="button" class="btn-primary" data-ver="${url}" style="padding:8px 12px;margin-right:6px">Ver</button>
      <a class="btn-primary" href="${url}" download="receta_${esc((r.creada || '').slice(0, 10))}_${r.id}.jpg" style="display:inline-block;padding:8px 12px;text-decoration:none">Descargar</a></div></article>`;
  }
  async function pintar(cont, estado, uid) {
    URLs.splice(0).forEach(u => URL.revokeObjectURL(u));
    const lista = (await todas()).filter(r => r.uid === String(uid)).sort((a, b) => String(b.creada).localeCompare(String(a.creada)));
    cont.innerHTML = lista.length ? lista.map(tarjeta).join('') : '<p class="muted">Aún no tienes recetas guardadas. Cuando escanees una y la aceptes, queda aquí.</p>';
    if (estado) estado.textContent = lista.length ? `${lista.length} receta(s) guardadas también en este teléfono, para verlas sin internet.` : '';
  }
  async function pintarSeccion() {
    const cont = g('bibliotecaLista'); if (!cont || !idUsuario) return;
    await pintar(cont, g('bibliotecaEstado'), idUsuario);
  }
  function visor(url) {
    const o = document.createElement('div');
    o.style.cssText = 'position:fixed;inset:0;z-index:3000;background:rgba(0,0,0,.92);display:flex;align-items:center;justify-content:center;padding:12px';
    o.innerHTML = `<img src="${url}" alt="Receta" style="max-width:100%;max-height:100%;object-fit:contain"><button type="button" style="position:absolute;top:14px;right:14px;padding:10px 16px;border-radius:10px;border:0;font-size:16px">Cerrar</button>`;
    o.addEventListener('click', () => o.remove());
    document.body.append(o);
  }
  document.addEventListener('click', e => { const v = e.target.closest && e.target.closest('[data-ver]'); if (v) visor(v.dataset.ver); });

  // Seccion dentro del panel
  g('btnActualizarBiblioteca')?.addEventListener('click', async () => {
    const est = g('bibliotecaEstado'); if (est) est.textContent = 'Actualizando...';
    const ok = await sincronizar(); await pintarSeccion();
    if (!ok && est) est.textContent = 'Sin internet: se muestran las recetas guardadas en este teléfono.';
  });
  let sesionSincronizada = null;
  setInterval(async () => {
    const panel = g('vistaPanel');
    if (!accessToken || !idUsuario || !panel || panel.classList.contains('hidden')) return;
    const marca = `${idUsuario}:${sesion}`;
    if (sesionSincronizada === marca) return;
    sesionSincronizada = marca;
    const ok = await sincronizar(); await pintarSeccion();
    if (!ok) { sesionSincronizada = null; const est = g('bibliotecaEstado'); if (est) est.textContent = 'Sin internet: se muestran las recetas guardadas en este teléfono.'; }
  }, 3000);
  window.addEventListener('online', async () => { sesionSincronizada = null; });

  // Al cerrar sesion se borra la copia de ese usuario (otra persona podria usar el telefono).
  ['btnSalir', 'btnSalirStaff'].forEach(id => g(id)?.addEventListener('click', () => { if (idUsuario) delUsuario(idUsuario); }, true));

  // Sin internet y sin sesion abierta: boton para ver las recetas guardadas en el telefono.
  const boton = document.createElement('button');
  boton.type = 'button';
  boton.textContent = 'Sin internet: ver mis recetas guardadas';
  boton.style.cssText = 'display:none;position:fixed;left:50%;transform:translateX(-50%);bottom:18px;z-index:2000;padding:12px 18px;border-radius:999px;border:0;background:#073B30;color:#fff;font:600 14px system-ui,sans-serif;box-shadow:0 6px 18px rgba(0,0,0,.25)';
  document.body.append(boton);
  async function actualizarBoton() {
    const auth = g('vistaAuth');
    const enLogin = auth && !auth.classList.contains('hidden');
    const uid = localStorage.getItem('taco_id');
    boton.style.display = (enLogin && uid && (await todas()).some(r => r.uid === uid)) ? '' : 'none';
  }
  setInterval(actualizarBoton, 2000);
  boton.addEventListener('click', async () => {
    const uid = localStorage.getItem('taco_id');
    const o = document.createElement('div');
    o.style.cssText = 'position:fixed;inset:0;z-index:2500;background:#fff;overflow:auto;padding:16px';
    o.innerHTML = '<h2 style="color:#073B30">Mis recetas guardadas</h2><p class="muted" id="offEstado"></p><div id="offLista"></div><button type="button" class="btn-primary" id="offCerrar" style="margin:12px 0 30px">Volver</button>';
    document.body.append(o);
    await pintar(o.querySelector('#offLista'), o.querySelector('#offEstado'), uid);
    o.querySelector('#offCerrar').onclick = () => o.remove();
  });
})();
