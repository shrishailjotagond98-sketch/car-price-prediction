(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const inr = (n) => "₹" + Math.round(n).toLocaleString("en-IN");
  const num = (n) => Number(n).toLocaleString("en-IN");

  let options = null;
  let historyRows = [];
  const charts = {};

  // ---------- helpers ----------
  async function api(path, opts = {}) {
    const res = await fetch("/api" + path, {
      headers: { "Content-Type": "application/json" },
      ...opts,
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || "Something went wrong. Try again.");
    return data;
  }

  let toastTimer;
  function toast(msg) {
    const t = $("toast");
    t.textContent = msg;
    t.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => (t.hidden = true), 2600);
  }

  function fillSelect(sel, items, placeholder) {
    sel.innerHTML = "";
    if (placeholder) sel.add(new Option(placeholder, ""));
    items.forEach((v) => sel.add(new Option(v, v)));
  }

  // ---------- router ----------
  const routes = ["home", "predict", "history", "analytics"];
  const loaders = { home: loadHome, predict: loadPredict, history: loadHistory, analytics: loadAnalytics };

  function route() {
    const name = (location.hash.replace("#/", "") || "home");
    const current = routes.includes(name) ? name : "home";
    routes.forEach((r) => ($("view-" + r).hidden = r !== current));
    document.querySelectorAll(".nav a").forEach((a) => {
      const active = a.dataset.route === current;
      a.classList.toggle("active", active);
      if (active) a.setAttribute("aria-current", "page");
      else a.removeAttribute("aria-current");
    });
    window.scrollTo(0, 0);
    loaders[current]().catch((e) => toast(e.message));
  }

  // ---------- home ----------
  async function loadHome() {
    const s = await api("/summary");
    $("sRows").textContent = num(s.rows);
    $("sBrands").textContent = s.brands;
    $("sR2").textContent = s.r2.toFixed(2);
    $("sMae").textContent = "±" + inr(s.mae);
    updateNavCount(s.predictions);
    if (s.last) {
      $("tagTitle").textContent = `${s.last.name}, ${s.last.year}`;
      $("tagPrice").textContent = inr(s.last.price);
      $("tagRange").textContent = `Likely range ${inr(s.last.low)} to ${inr(s.last.high)}`;
    }
  }

  function updateNavCount(n) {
    const b = $("navCount");
    b.textContent = n;
    b.hidden = !n;
  }

  // ---------- predict ----------
  async function loadPredict() {
    if (options) return;
    options = await api("/options");
    fillSelect($("fCompany"), options.companies, "Choose a brand");
    fillSelect($("fName"), [], "Choose a brand first");
    fillSelect($("fFuel"), [], "Choose a model first");
    const y = $("fYear");
    y.min = options.year_min;
    y.max = options.year_max;
    y.placeholder = `${options.year_min} to ${options.year_max}`;
  }

  $("fCompany").addEventListener("change", (e) => {
    const list = options.models[e.target.value] || [];
    fillSelect($("fName"), list, list.length ? "Choose a model" : "Choose a brand first");
    fillSelect($("fFuel"), [], "Choose a model first");
  });

  $("fName").addEventListener("change", (e) => {
    const fuels = (options.model_fuels[$("fCompany").value] || {})[e.target.value] || [];
    fillSelect($("fFuel"), fuels, fuels.length ? "Choose fuel type" : "Choose a model first");
  });

  function showError(msg) {
    const el = $("formError");
    el.textContent = msg || "";
    el.hidden = !msg;
  }

  $("predictForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    showError("");
    const body = {
      company: $("fCompany").value,
      name: $("fName").value,
      year: $("fYear").value,
      kms_driven: $("fKms").value,
      fuel_type: $("fFuel").value,
    };
    if (!body.company) return showError("Choose a brand.");
    if (!body.name) return showError("Choose a model.");
    if (!body.year) return showError("Enter the year the car was made.");
    if (body.kms_driven === "") return showError("Enter the kilometres driven.");
    if (!body.fuel_type) return showError("Choose a fuel type.");

    const btn = $("predictBtn");
    btn.disabled = true;
    btn.textContent = "Estimating…";
    try {
      const r = await api("/predict", { method: "POST", body: JSON.stringify(body) });
      showResult(body, r);
      toast("Estimate saved to History");
    } catch (err) {
      showError(err.message);
    } finally {
      btn.disabled = false;
      btn.textContent = "Estimate price";
    }
  });

  function showResult(body, r) {
    $("resultEmpty").hidden = true;
    $("resultBody").hidden = false;
    $("rCar").textContent = `${body.name}, ${body.year}, ${num(body.kms_driven)} km, ${body.fuel_type}`;
    $("rPrice").textContent = inr(r.price);
    $("rLow").textContent = inr(r.low);
    $("rHigh").textContent = inr(r.high);
    const span = Math.max(r.high - r.low, 1);
    const pos = Math.min(100, Math.max(0, ((r.price - r.low) / span) * 100));
    document.querySelector(".range-dot").style.left = pos + "%";
    $("rNote").textContent = "About eight in ten validation listings fell inside this range. Treat it as an estimate; actual prices depend on condition and local market.";
  }

  // ---------- history ----------
  async function loadHistory() {
    historyRows = await api("/history");
    updateNavCount(historyRows.length);
    renderHistory();
  }

  function renderHistory() {
    const q = $("histSearch").value.trim().toLowerCase();
    const rows = historyRows.filter((r) =>
      !q || `${r.company} ${r.name} ${r.fuel_type} ${r.year}`.toLowerCase().includes(q)
    );
    const body = $("histBody");
    body.innerHTML = "";
    rows.forEach((r) => {
      const tr = document.createElement("tr");
      const cells = [
        [new Date(r.created_at).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" }), ""],
        [r.name, "car"],
        [r.year, ""],
        [num(r.kms_driven), "num"],
        [r.fuel_type, ""],
        [inr(r.price), "num price"],
        [`${inr(r.low)} to ${inr(r.high)}`, "num"],
      ];
      cells.forEach(([text, cls]) => {
        const td = document.createElement("td");
        td.textContent = text;
        if (cls) td.className = cls;
        tr.appendChild(td);
      });
      const td = document.createElement("td");
      const del = document.createElement("button");
      del.className = "del";
      del.textContent = "Delete";
      del.setAttribute("aria-label", `Delete estimate for ${r.name}`);
      del.addEventListener("click", async () => {
        await api("/history/" + r.id, { method: "DELETE" });
        toast("Estimate deleted");
        loadHistory();
      });
      td.appendChild(del);
      tr.appendChild(td);
      body.appendChild(tr);
    });
    $("histEmpty").hidden = rows.length > 0;
    $("histSub").textContent = historyRows.length
      ? `${historyRows.length} saved estimate${historyRows.length === 1 ? "" : "s"}, newest first.`
      : "Every estimate you make is saved here.";
    $("exportBtn").disabled = !historyRows.length;
    $("clearBtn").disabled = !historyRows.length;
  }

  $("histSearch").addEventListener("input", renderHistory);

  $("clearBtn").addEventListener("click", async () => {
    if (!confirm("Delete all saved estimates? This cannot be undone.")) return;
    await api("/history", { method: "DELETE" });
    toast("History cleared");
    loadHistory();
  });

  $("exportBtn").addEventListener("click", () => {
    const head = ["Date", "Brand", "Model", "Year", "Kms driven", "Fuel", "Estimate", "Low", "High"];
    const esc = (v) => `"${String(v).replace(/"/g, '""')}"`;
    const lines = historyRows.map((r) =>
      [r.created_at, r.company, r.name, r.year, r.kms_driven, r.fuel_type, r.price, r.low, r.high].map(esc).join(",")
    );
    const blob = new Blob([[head.map(esc).join(","), ...lines].join("\n")], { type: "text/csv" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "car-price-history.csv";
    a.click();
    URL.revokeObjectURL(a.href);
  });

  // ---------- analytics ----------
  const PALETTE = ["#0f766e", "#f2b632", "#12222b", "#6aa9a3", "#c98a00"];

  function draw(id, config) {
    if (charts[id]) charts[id].destroy();
    charts[id] = new Chart($(id), config);
  }

  async function loadAnalytics() {
    const a = await api("/analytics");
    const mine = a.my_predictions;
    $("aCount").textContent = mine.count;
    $("aAvg").textContent = mine.count ? inr(mine.avg_price) : "-";
    $("aBrand").textContent = mine.top_brand || "-";
    $("aModel").textContent = a.model.best_model;
    updateNavCount(mine.count);

    if (typeof Chart === "undefined") {
      $("chartWarn").hidden = false;
      return;
    }
    $("chartWarn").hidden = true;
    Chart.defaults.font.family = '"Instrument Sans", system-ui, sans-serif';
    Chart.defaults.color = "#5b6b70";

    const lakh = (v) => "₹" + (v / 100000).toFixed(1) + "L";
    const priceTick = { callback: lakh };
    const tipInr = { callbacks: { label: (c) => " " + inr(c.parsed.y ?? c.parsed) } };

    draw("cBrand", {
      type: "bar",
      data: {
        labels: a.by_brand.map((r) => r.company),
        datasets: [{ data: a.by_brand.map((r) => r.avg_price), backgroundColor: PALETTE[0], borderRadius: 4 }],
      },
      options: {
        maintainAspectRatio: false, indexAxis: "y",
        plugins: { legend: { display: false }, tooltip: { callbacks: { label: (c) => " " + inr(c.parsed.x) } } },
        scales: { x: { ticks: priceTick, grid: { color: "#e6ecea" } }, y: { grid: { display: false } } },
      },
    });

    draw("cYear", {
      type: "line",
      data: {
        labels: a.by_year.map((r) => r.year),
        datasets: [{ data: a.by_year.map((r) => r.avg_price), borderColor: PALETTE[0], backgroundColor: "rgba(15,118,110,.12)", fill: true, tension: .3, pointRadius: 3 }],
      },
      options: {
        maintainAspectRatio: false,
        plugins: { legend: { display: false }, tooltip: tipInr },
        scales: { y: { ticks: priceTick, grid: { color: "#e6ecea" } }, x: { grid: { display: false } } },
      },
    });

    $("fuelNote").textContent = a.fuel.map((f) => `${f.fuel_type}: avg ${inr(f.avg_price)}`).join(", ");
    draw("cFuel", {
      type: "doughnut",
      data: {
        labels: a.fuel.map((f) => f.fuel_type),
        datasets: [{ data: a.fuel.map((f) => f.count), backgroundColor: PALETTE, borderWidth: 2, borderColor: "#fff" }],
      },
      options: { maintainAspectRatio: false, cutout: "62%", plugins: { legend: { position: "bottom" } } },
    });

    draw("cKms", {
      type: "scatter",
      data: { datasets: [{ data: a.kms_price, backgroundColor: "rgba(15,118,110,.55)", pointRadius: 3 }] },
      options: {
        maintainAspectRatio: false,
        plugins: { legend: { display: false }, tooltip: { callbacks: { label: (c) => ` ${num(c.parsed.x)} km, ${inr(c.parsed.y)}` } } },
        scales: {
          x: { title: { display: true, text: "Kilometres driven" }, ticks: { callback: (v) => v / 1000 + "k" }, grid: { color: "#e6ecea" } },
          y: { ticks: priceTick, grid: { color: "#e6ecea" } },
        },
      },
    });

    const pts = a.model.test_points.map((p) => ({ x: p.actual, y: p.predicted }));
    const top = Math.max(...pts.map((p) => Math.max(p.x, p.y)));
    $("modelNote").textContent =
      `${a.model.best_model} scored R² ${a.model.r2.toFixed(2)} on cars it never saw, with a typical error of ${inr(a.model.mae)}. Dots close to the line are good predictions.`;
    draw("cModel", {
      type: "scatter",
      data: {
        datasets: [
          { label: "Test cars", data: pts, backgroundColor: "rgba(15,118,110,.6)", pointRadius: 4 },
          { label: "Perfect prediction", type: "line", data: [{ x: 0, y: 0 }, { x: top, y: top }], borderColor: PALETTE[1], borderWidth: 2, pointRadius: 0 },
        ],
      },
      options: {
        maintainAspectRatio: false,
        plugins: { legend: { position: "bottom" }, tooltip: { callbacks: { label: (c) => ` actual ${inr(c.parsed.x)}, predicted ${inr(c.parsed.y)}` } } },
        scales: {
          x: { title: { display: true, text: "Actual price" }, ticks: priceTick, grid: { color: "#e6ecea" } },
          y: { title: { display: true, text: "Predicted price" }, ticks: priceTick, grid: { color: "#e6ecea" } },
        },
      },
    });
  }

  window.addEventListener("hashchange", route);
  route();
})();
