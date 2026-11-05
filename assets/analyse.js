/* Bezoekersstatistiek met Google Analytics — alleen na toestemming.
   Zonder toestemming wordt er niets van Google geladen en worden er geen cookies gezet.
   window.SA_ANALYSE = {id, t: {tekst, ja, nee, meer, privacy}} wordt per pagina gezet. */
(function () {
  "use strict";
  const A = window.SA_ANALYSE;
  if (!A || !A.id) return;
  const SLEUTEL = "sa-analyse";
  const lees = () => { try { return localStorage.getItem(SLEUTEL); } catch (e) { return null; } };
  const zet = v => { try { localStorage.setItem(SLEUTEL, v); } catch (e) {} };

  function laadGoogle() {
    if (window.gtag) return;
    window.dataLayer = window.dataLayer || [];
    window.gtag = function () { window.dataLayer.push(arguments); };
    gtag("consent", "default", {ad_storage: "denied", ad_user_data: "denied", ad_personalization: "denied",
                                analytics_storage: "granted"});
    gtag("js", new Date());
    gtag("config", A.id, {allow_google_signals: false, allow_ad_personalization_signals: false});
    const s = document.createElement("script");
    s.async = true;
    s.src = "https://www.googletagmanager.com/gtag/js?id=" + encodeURIComponent(A.id);
    document.head.appendChild(s);
  }
  function wisCookies() {
    // _ga-cookies van een eerdere toestemming weghalen
    document.cookie.split(";").map(c => c.split("=")[0].trim()).filter(n => /^_ga/.test(n)).forEach(n => {
      const domeinen = [location.hostname, "." + location.hostname];
      for (const d of domeinen) document.cookie = `${n}=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/; domain=${d}`;
      document.cookie = `${n}=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/`;
    });
  }
  function balk() {
    if (document.getElementById("sa-toestemming")) return;
    const d = document.createElement("div");
    d.id = "sa-toestemming";
    d.setAttribute("role", "region");
    d.setAttribute("aria-label", A.t.meer);
    d.innerHTML = `<p>${A.t.tekst} <a href="${A.t.privacy}">${A.t.meer}</a></p>
<div class="sa-knoppen"><button type="button" data-keuze="ja">${A.t.ja}</button><button type="button" data-keuze="nee">${A.t.nee}</button></div>`;
    d.addEventListener("click", e => {
      const k = e.target.closest("[data-keuze]");
      if (!k) return;
      zet(k.dataset.keuze);
      d.remove();
      if (k.dataset.keuze === "ja") laadGoogle(); else wisCookies();
    });
    document.body.appendChild(d);
  }
  // knop in de voettekst en op de privacypagina: keuze opnieuw maken
  document.addEventListener("click", e => {
    if (e.target.closest("[data-sa-instellingen]")) { e.preventDefault(); balk(); }
  });
  const keuze = lees();
  if (keuze === "ja") laadGoogle();
  else if (keuze !== "nee") {
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", balk); else balk();
  }
})();
