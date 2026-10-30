// ============================================================
// AQUASENTINEL — FRONTEND ↔ FLASK API
// ============================================================

let levelChart = null;


// ============================================================
// GET ELEMENT
// ============================================================

function $(id) {
    return document.getElementById(id);
}


// ============================================================
// CONNECTION STATUS
// ============================================================

function updateConnection(status) {

    const dot = $("connectionDot");
    const text = $("connectionText");

    if (!dot || !text) return;

    if (status === "online") {

        dot.classList.remove("offline");
        dot.classList.add("online");

        text.textContent = "Connected";

    } else if (status === "waiting") {

        dot.classList.remove("offline");
        dot.classList.add("online");

        text.textContent = "Waiting for data";

    } else {

        dot.classList.remove("online");
        dot.classList.add("offline");

        text.textContent = "Disconnected";
    }
}


// ============================================================
// GET LATEST READING
// ============================================================

async function getLatest() {

    const response = await fetch("/api/latest", {
        cache: "no-store"
    });

    if (response.status === 404) {
        throw new Error("NO_DATA");
    }

    if (!response.ok) {
        throw new Error("API_ERROR");
    }

    return await response.json();
}


// ============================================================
// GET HISTORY
// ============================================================

async function getHistory() {

    const response = await fetch(
        "/api/history?limit=30",
        {
            cache: "no-store"
        }
    );

    if (!response.ok) {
        throw new Error("HISTORY_ERROR");
    }

    return await response.json();
}


// ============================================================
// RISK COLOR
// ============================================================

function riskColor(level) {

    switch (String(level).toUpperCase()) {

        case "LOW":
            return "#34d399";

        case "MODERATE":
            return "#facc15";

        case "HIGH":
            return "#fb923c";

        case "CRITICAL":
            return "#fb7185";

        default:
            return "#22d3ee";
    }
}


// ============================================================
// UPDATE RISK
// ============================================================

function updateRisk(data) {

    const score = Number(data.risk_score);
    const level = String(data.risk_level).toUpperCase();

    updateCursorRisk(level);

    $("riskScore").textContent = score.toFixed(1);
    $("riskLevel").textContent = level;

    $("scoreMini").textContent = score.toFixed(1);
    $("scoreStatus").textContent = level;

    // Risk description
    const descriptions = {

        LOW:
            "Environmental conditions are currently stable.",

        MODERATE:
            "Moderate flood risk detected. Continue monitoring.",

        HIGH:
            "High flood risk detected. Prepare for possible action.",

        CRITICAL:
            "Critical flood risk detected. Immediate action recommended."
    };

    $("riskDescription").textContent =
        descriptions[level] ||
        "Awaiting sensor data";


    // Risk bar
    $("scoreBar").style.width =
        `${Math.min(score, 100)}%`;


    // Risk color
    const color = riskColor(level);

    $("riskCard").style.setProperty(
        "--risk-color",
        color
    );


    // Critical animation
    if (level === "CRITICAL") {

        document.body.classList.add(
            "critical-mode"
        );

    } else {

        document.body.classList.remove(
            "critical-mode"
        );
    }
    
}


// ============================================================
// UPDATE SENSOR CARDS
// ============================================================

function updateSensors(data) {

    const water = Number(data.water_level);
    const rise = Number(data.rise_rate);
    const rain = Number(data.rain);
    const temperature = Number(data.temperature);
    const humidity = Number(data.humidity);


    // WATER
    $("waterLevel").textContent =
        `${water.toFixed(1)}%`;

    $("riseRate").textContent =
        `Rise: ${rise.toFixed(2)} cm/min`;

    $("waterProgress").style.width =
        `${Math.min(water, 100)}%`;


    // RAIN
    if (rain >= 1) {

        $("rain").textContent =
            "DETECTED";

        $("rainDetail").textContent =
            "Rain detected";

    } else {

        $("rain").textContent =
            "NONE";

        $("rainDetail").textContent =
            "No rainfall";
    }


    // TEMPERATURE
    $("temperature").textContent =
        `${temperature.toFixed(1)}°C`;


    // HUMIDITY
    $("humidity").textContent =
        `${humidity.toFixed(1)}%`;
}


// ============================================================
// UPDATE PREDICTION
// ============================================================

function updatePrediction(data) {

    const predicted =
        Number(data.predicted_level);

    const probability =
        Number(data.ml_high_risk_probability);


    $("predictedLevel").textContent =
        `${predicted.toFixed(1)}%`;


    $("mlProbability").textContent =
        `${probability.toFixed(1)}%`;
}


// ============================================================
// UPDATE DECISION
// ============================================================

function updateDecision(data) {

    const level =
        String(data.risk_level).toUpperCase();

    const gate =
        String(data.gate_status).toUpperCase();


    // Gate
    $("gateStatus").textContent =
        gate;


    // Recommendation
    const recommendations = {

        LOW:
            "Continue normal monitoring.",

        MODERATE:
            "Monitor water level and rainfall closely.",

        HIGH:
            "Prepare for possible flood response.",

        CRITICAL:
            "Immediate protective action recommended."
    };


    $("recommendation").textContent =
        recommendations[level] ||
        "Waiting for data";


    // Timestamp
    if (data.timestamp) {

        const date =
            new Date(data.timestamp);

        $("lastUpdate").textContent =
            date.toLocaleTimeString();
    }
}


// ============================================================
// UPDATE ALERT
// ============================================================

function updateAlert(data) {

    const level =
        String(data.risk_level).toUpperCase();


    const title = $("alertTitle");
    const text = $("alertText");


    if (level === "LOW") {

        title.textContent =
            "SYSTEM STABLE";

        text.textContent =
            "Water and environmental conditions are currently within safe limits.";

    }

    else if (level === "MODERATE") {

        title.textContent =
            "MODERATE RISK";

        text.textContent =
            "Environmental conditions require continued monitoring.";

    }

    else if (level === "HIGH") {

        title.textContent =
            "HIGH FLOOD RISK";

        text.textContent =
            "Rapidly changing conditions detected. Prepare for possible action.";

    }

    else if (level === "CRITICAL") {

        title.textContent =
            "CRITICAL FLOOD RISK";

        text.textContent =
            "Immediate protective action is recommended.";

    }
}


// ============================================================
// UPDATE EVERYTHING
// ============================================================

function updateDashboard(data) {

    console.log(
        "AquaSentinel reading:",
        data
    );

    updateRisk(data);

    updateSensors(data);

    updatePrediction(data);

    updateDecision(data);

    updateAlert(data);
}


// ============================================================
// CHART
// ============================================================

function updateChart(history) {

    const canvas =
        $("levelChart");

    if (!canvas) {
        console.warn(
            "levelChart canvas not found."
        );
        return;
    }


    // Chart.js must be loaded
    if (typeof Chart === "undefined") {

        console.warn(
            "Chart.js is not loaded."
        );

        return;
    }


    const labels =
        history.map(item => {

            const date =
                new Date(item.timestamp);

            return date.toLocaleTimeString();
        });


    const waterLevels =
        history.map(item =>
            Number(item.water_level)
        );


    // First time
    if (!levelChart) {

        levelChart = new Chart(
            canvas,
            {

                type: "line",

                data: {

                    labels: labels,

                    datasets: [

                        {

                            label:
                                "Water Level (%)",

                            data:
                                waterLevels,

                            borderWidth: 2,

                            tension: 0.35,

                            fill: true
                        }

                    ]
                },

                options: {

                    responsive: true,

                    maintainAspectRatio: false,

                    animation: {
                        duration: 400
                    },

                    scales: {

                        y: {

                            beginAtZero: true,

                            max: 100
                        }

                    },

                    plugins: {

                        legend: {
                            display: true
                        }

                    }
                }

            }
        );

    }

    // Update existing chart
    else {

        levelChart.data.labels =
            labels;

        levelChart.data.datasets[0].data =
            waterLevels;

        levelChart.update();
    }
}


// ============================================================
// REFRESH
// ============================================================

async function refreshDashboard() {

    try {

        const data =
            await getLatest();


        // Backend + data available
        updateConnection("online");

        updateDashboard(data);


        // History
        try {

            const history =
                await getHistory();

            updateChart(history);

        }

        catch (error) {

            console.warn(
                "History error:",
                error
            );
        }

    }

    catch (error) {

        console.error(
            "Dashboard API error:",
            error
        );


        if (error.message === "NO_DATA") {

            updateConnection("waiting");

        }

        else {

            updateConnection("offline");
        }
    }
}


// ============================================================
// INITIALIZE
// ============================================================

window.addEventListener(
    "load",
    () => {

        console.log(
            "AquaSentinel frontend started."
        );


        // First update immediately
        refreshDashboard();


        // Update every 2 seconds
        setInterval(
            refreshDashboard,
            2000
        );
    }
);

/* ========================================
   AQUASENTINEL — DUAL CURSOR
======================================== */

const cursorGlow = document.querySelector(".cursor-glow");
const cursorRing = document.querySelector(".cursor-ring");

let mouseX = window.innerWidth / 2;
let mouseY = window.innerHeight / 2;
let glowX = mouseX;
let glowY = mouseY;

const hasFinePointer = window.matchMedia(
    "(hover: hover) and (pointer: fine)"
).matches;

if (
    cursorGlow &&
    cursorRing &&
    hasFinePointer &&
    !window.matchMedia("(prefers-reduced-motion: reduce)").matches
) {
    document.body.classList.add("custom-cursor");

    document.addEventListener("mousemove", (event) => {
        mouseX = event.clientX;
        mouseY = event.clientY;

        cursorRing.style.left = `${mouseX}px`;
        cursorRing.style.top = `${mouseY}px`;
    });

    function animateGlow() {
        // Smooth trailing movement
        glowX += (mouseX - glowX) * 0.10;
        glowY += (mouseY - glowY) * 0.10;

        cursorGlow.style.left = `${glowX}px`;
        cursorGlow.style.top = `${glowY}px`;

        requestAnimationFrame(animateGlow);
    }

    animateGlow();

    // Expand the cursor over clickable elements
    document.querySelectorAll(
        "a, button, .metric, .card"
    ).forEach((element) => {
        element.addEventListener("mouseenter", () => {
            cursorRing.classList.add("cursor-hover");
        });

        element.addEventListener("mouseleave", () => {
            cursorRing.classList.remove("cursor-hover");
        });
    });
}

/* Change cursor colours with flood risk */
function updateCursorRisk(level) {
    if (!cursorRing || !cursorGlow) return;

    const colors = {
        LOW: "#34d399",
        MODERATE: "#facc15",
        HIGH: "#fb923c",
        CRITICAL: "#fb7185"
    };

    const color = colors[String(level).toUpperCase()] || "#22d3ee";

    cursorRing.style.borderColor = color;
    cursorRing.style.boxShadow =
        `0 0 14px ${color}, 0 0 32px ${color}66`;

    cursorGlow.style.background =
        `radial-gradient(circle, ${color}30 0%, ${color}12 35%, transparent 72%)`;
}