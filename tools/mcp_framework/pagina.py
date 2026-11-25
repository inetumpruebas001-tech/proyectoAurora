"""
Captura de elementos interactivos de la página con locators sugeridos (formato del framework).
Lo usan explorar_pagina (URL directa) y explorador_behave.py (pantallas tras ejecutar steps).
"""

from __future__ import annotations

import json

_JS_ELEMENTOS = r"""
const solo = arguments[0];
const sel = 'input,button,select,textarea,a[href],[role=button],[role=link],[role=tab],[role=checkbox],[role=combobox],[contenteditable=true]';
const unico = (css) => { try { return document.querySelectorAll(css).length === 1; } catch(e) { return false; } };
const esc = (v) => (window.CSS && CSS.escape) ? CSS.escape(v) : v.replace(/([^\w-])/g,'\\$1');
const out = [];
for (const el of document.querySelectorAll(sel)) {
  const r = el.getBoundingClientRect();
  const visible = !!(r.width && r.height) && getComputedStyle(el).visibility !== 'hidden';
  if (solo && !visible) continue;
  const tag = el.tagName.toLowerCase();
  const texto = (el.innerText || el.value || '').trim().replace(/\s+/g,' ').slice(0,60);
  let label = el.getAttribute('aria-label') || el.getAttribute('placeholder') || '';
  if (!label && el.id) { const l = document.querySelector('label[for="'+el.id+'"]'); if (l) label = l.innerText.trim(); }
  let loc = null;
  if (el.id && unico('#'+esc(el.id))) loc = ['ID', el.id];
  else if (el.name && unico(tag+'[name="'+el.name+'"]')) loc = ['NAME', el.name];
  else {
    for (const a of ['data-testid','data-test','data-qa','aria-label','formcontrolname']) {
      const v = el.getAttribute(a);
      if (v && unico(tag+'['+a+'="'+v+'"]')) { loc = ['CSS_SELECTOR', tag+'['+a+'="'+v+'"]']; break; }
    }
  }
  if (!loc && tag === 'a' && texto && [...document.querySelectorAll('a')].filter(x => (x.innerText||'').trim() === texto).length === 1) loc = ['LINK_TEXT', texto];
  let xp = null, snap = null;
  if (!loc && texto && ['button','a'].includes(tag)) {
    xp = '//'+tag+'[normalize-space()="'+texto.replace(/"/g,"'")+'"]';
    snap = document.evaluate(xp, document, null, XPathResult.ORDERED_NODE_SNAPSHOT_TYPE, null);
    if (snap.snapshotLength === 1) loc = ['XPATH', xp];
  }
  if (!loc && el.className && typeof el.className === 'string' && el.className.trim()) {
    const css = tag + '.' + el.className.trim().split(/\s+/).map(esc).join('.');
    if (unico(css)) loc = ['CSS_SELECTOR', css];
  }
  if (!loc && snap && snap.snapshotLength > 1) {
    for (let i = 0; i < snap.snapshotLength; i++) { if (snap.snapshotItem(i) === el) { loc = ['XPATH', '('+xp+')['+(i+1)+']']; break; } }
  }
  out.push({tag, type: el.getAttribute('type') || '', texto, label, visible, locator: loc,
            fragil: !!(loc && (loc[0] === 'XPATH' && loc[1].startsWith('(') || loc[0] === 'CSS_SELECTOR' && /\.btn/.test(loc[1])))});
  if (out.length >= 120) break;
}
return out;
"""


def capturar(driver, solo_visibles: bool = True) -> dict:
    elementos = driver.execute_script(_JS_ELEMENTOS, solo_visibles) or []
    iframes = len(driver.find_elements("tag name", "iframe"))
    for e in elementos:
        if e.get("locator"):
            by, valor = e["locator"]
            e["locator_python"] = f"(By.{by}, {json.dumps(valor, ensure_ascii=False)})"
        e.pop("locator", None)
        if e.get("type") == "password":
            e["texto"] = ""
    return {
        "url_final": driver.current_url,
        "titulo": driver.title,
        "iframes": iframes,
        "aviso_iframes": "Hay iframes: los elementos internos requieren driver.switch_to.frame(...)" if iframes else "",
        "total": len(elementos),
        "elementos": elementos,
    }
