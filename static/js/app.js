// static/js/app.js

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

let trendChart = null;
let hdbMap = null;
let amenityMarkers = [];
let townPolygons = [];
let listingMarkers = [];
let compareTownMarkers = [];
let amenitiesData = null;
let currentListingPopup = null;
let lastAffordSignature = null;

// Amenity icon configurations
const AMENITY_ICONS = {
  'MRT_STATION': { icon: '🚇', color: '#dc2626', label: 'MRT Station' },
  'SCHOOL': { icon: '🏫', color: '#2563eb', label: 'School' },
  'CLINIC': { icon: '🏥', color: '#059669', label: 'Clinic' },
  'SUPERMARKET': { icon: '🛒', color: '#ea580c', label: 'Supermarket' },
  'PARK': { icon: '🌳', color: '#16a34a', label: 'Park' },
  'DEFAULT': { icon: '📍', color: '#10b981', label: 'Amenity' }
};

// ========== MAPBOX INITIALIZATION ==========
function initMapbox() {
  const mapEl = document.getElementById("map");
  if (!mapEl || typeof mapboxgl === "undefined") {
    console.warn("Map element or Mapbox GL not available");
    return;
  }

  mapboxgl.accessToken = "pk.eyJ1IjoieGVyeGVzMTY4IiwiYSI6ImNtaGxxcDUyMjBuZnQybXNpejlrOW42ODEifQ.spgJB7Tvse-NB1QDFnWDRw";

  hdbMap = new mapboxgl.Map({
    container: mapEl,
    style: "mapbox://styles/mapbox/light-v11",
    center: [103.8198, 1.3521],
    zoom: 10.5,
  });

  hdbMap.addControl(new mapboxgl.NavigationControl(), "top-right");
  hdbMap.addControl(new mapboxgl.FullscreenControl(), "top-right");

  hdbMap.on("load", () => {
    hdbMap.resize();
  });
}

function clearAmenityMarkers() {
  amenityMarkers.forEach(m => m.remove());
  amenityMarkers = [];
}

function clearTownPolygons() {
  townPolygons.forEach(layerId => {
    if (hdbMap.getLayer(layerId)) {
      hdbMap.removeLayer(layerId);
    }
    if (hdbMap.getLayer(`${layerId}-outline`)) {
      hdbMap.removeLayer(`${layerId}-outline`);
    }
    if (hdbMap.getSource(layerId)) {
      hdbMap.removeSource(layerId);
    }
  });
  townPolygons = [];
}

function clearListingMarkers() {
  listingMarkers.forEach(m => m.remove());
  listingMarkers = [];
  if (currentListingPopup) {
    currentListingPopup.remove();
    currentListingPopup = null;
  }
}

function clearCompareTownHighlights() {
  if (!hdbMap) return;

  // Remove compare markers
  compareTownMarkers.forEach(m => {
    if (m && typeof m.remove === "function") {
      m.remove();
    }
  });
  compareTownMarkers = [];

  // Remove compare layers and sources if they exist
  if (hdbMap.getLayer("compare-towns-fill")) {
    hdbMap.removeLayer("compare-towns-fill");
  }
  if (hdbMap.getLayer("compare-towns-outline")) {
    hdbMap.removeLayer("compare-towns-outline");
  }
  if (hdbMap.getSource("compare-towns-source")) {
    hdbMap.removeSource("compare-towns-source");
  }
}

function getAmenityConfig(amenityType) {
  const type = amenityType ? amenityType.toUpperCase() : 'DEFAULT';
  return AMENITY_ICONS[type] || AMENITY_ICONS['DEFAULT'];
}
function getPriceRange(price) {
  const numericPrice = typeof price === 'number' ? price : parseFloat(price || '0');
  if (!numericPrice || Number.isNaN(numericPrice)) {
    return null;
  }
  const min = Math.round(numericPrice * 0.95 / 1000) * 1000;
  const max = Math.round(numericPrice * 1.05 / 1000) * 1000;
  return {
    min,
    max,
    label: `$${min.toLocaleString()} – $${max.toLocaleString()}`
  };
}

function distanceInMeters(lat1, lng1, lat2, lng2) {
  const R = 6371000; // earth radius in meters
  const toRad = (d) => (d * Math.PI) / 180;

  const dLat = toRad(lat2 - lat1);
  const dLng = toRad(lng2 - lng1);
  const a =
    Math.sin(dLat / 2) * Math.sin(dLat / 2) +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) *
    Math.sin(dLng / 2) * Math.sin(dLng / 2);

  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  return R * c;
}

function getNearbyAmenities(lat, lng, radiusMeters = 600) {
  if (!amenitiesData || !amenitiesData.features) return [];

  return amenitiesData.features.filter((f) => {
    if (!f || !f.geometry || f.geometry.type !== 'Point') return false;
    const coords = f.geometry.coordinates || [];
    if (!Array.isArray(coords) || coords.length < 2) return false;
    const [fLng, fLat] = coords;
    const dist = distanceInMeters(lat, lng, fLat, fLng);
    return dist <= radiusMeters;
  });
}

function showNearbyAmenitiesOnMap(lat, lng, radiusMeters = 600) {
  if (!hdbMap) return [];

  const nearby = getNearbyAmenities(lat, lng, radiusMeters);
  clearAmenityMarkers();

  if (!nearby.length) {
    return [];
  }

  const drawable = [];
  const coordCounts = {};

  nearby.forEach((feature) => {
    const geom = feature.geometry;
    const props = feature.properties || {};
    if (!geom || geom.type !== "Point" || !Array.isArray(geom.coordinates)) return;

    let [fLng, fLat] = geom.coordinates;

    // Track how many amenities share this exact coordinate (rounded to 6dp)
    const key = `${fLng.toFixed(6)},${fLat.toFixed(6)}`;
    coordCounts[key] = (coordCounts[key] || 0) + 1;
    const indexAtCoord = coordCounts[key];

    // If multiple amenities share the same spot, jitter them slightly
    if (indexAtCoord > 1) {
      const offsetMeters = 18; // ~18m radius circle
      const angle = (indexAtCoord - 1) * (Math.PI / 3); // 6 positions around the circle

      // Rough meter-to-degree conversion
      const metersPerDegLat = 111320;
      const metersPerDegLng = 111320 * Math.cos((fLat * Math.PI) / 180);

      const dLat = (offsetMeters * Math.sin(angle)) / metersPerDegLat;
      const dLng = (offsetMeters * Math.cos(angle)) / metersPerDegLng;

      fLat = fLat + dLat;
      fLng = fLng + dLng;
    }

    const amenityType = props.CLASS || props.amenity_type || "DEFAULT";
    const config = getAmenityConfig(amenityType);
    const name = props.NAME || props.name || "Unnamed amenity";

    const el = document.createElement("div");
    el.className = "amenity-marker-custom";
    el.style.backgroundColor = config.color;
    el.innerHTML = `<span class="amenity-icon">${config.icon}</span>`;

    const popupHtml = `
      <div style="min-width: 220px;">
        <div style="font-weight: 600; margin-bottom: 6px; color: #18181b; font-size: 14px;">
          ${config.icon} ${name}
        </div>
        <div style="font-size: 12px; color: #52525b; margin-bottom: 4px;">
          Type: <span style="font-weight: 600; color: ${config.color};">${config.label}</span>
        </div>
        <div style="font-size: 11px; color: #71717a;">
          ${geom.coordinates[0].toFixed(5)}, ${geom.coordinates[1].toFixed(5)}
        </div>
      </div>
    `;

    const popup = new mapboxgl.Popup({ offset: 16 }).setHTML(popupHtml);

    const marker = new mapboxgl.Marker(el)
      .setLngLat([fLng, fLat])
      .setPopup(popup)
      .addTo(hdbMap);

    amenityMarkers.push(marker);
    drawable.push(feature);
  });

  return drawable;
}

function showAmenitiesOnMap(geojson) {
  if (!hdbMap || !geojson || !geojson.features) return;

  clearAmenityMarkers();

  const coordsList = [];
  const amenityCount = geojson.features.length;

  geojson.features.forEach((feature) => {
    const geom = feature.geometry;
    const props = feature.properties || {};
    if (!geom || geom.type !== "Point" || !Array.isArray(geom.coordinates)) return;

    const [lng, lat] = geom.coordinates;
    coordsList.push([lng, lat]);

    const amenityType = props.CLASS || props.amenity_type || "DEFAULT";
    const config = getAmenityConfig(amenityType);
    const name = props.NAME || props.name || "Unnamed amenity";

    const el = document.createElement("div");
    el.className = "amenity-marker-custom";
    el.style.backgroundColor = config.color;
    el.innerHTML = `<span class="amenity-icon">${config.icon}</span>`;

    const popupHtml = `
      <div style="min-width: 220px;">
        <div style="font-weight: 600; margin-bottom: 6px; color: #18181b; font-size: 14px;">
          ${config.icon} ${name}
        </div>
        <div style="font-size: 12px; color: #52525b; margin-bottom: 4px;">
          Type: <span style="font-weight: 600; color: ${config.color};">${config.label}</span>
        </div>
        <div style="font-size: 11px; color: #71717a;">
          ${lng.toFixed(5)}, ${lat.toFixed(5)}
        </div>
      </div>
    `;

    const popup = new mapboxgl.Popup({ offset: 16 }).setHTML(popupHtml);

    const marker = new mapboxgl.Marker(el)
      .setLngLat([lng, lat])
      .setPopup(popup)
      .addTo(hdbMap);

    amenityMarkers.push(marker);
  });

  if (coordsList.length > 0) {
    const bounds = coordsList.reduce(
      (b, c) => b.extend(c),
      new mapboxgl.LngLatBounds(coordsList[0], coordsList[0])
    );
    hdbMap.fitBounds(bounds, { padding: 40, maxZoom: 15 });
  }

  // Update stats display
  updateAmenityStats(amenityCount);
}

function showTownBoundariesOnMap(towns) {
  if (!hdbMap || !towns || towns.length === 0) {
    console.warn('Cannot show town boundaries:', { hdbMap, towns });
    return;
  }

  console.log('Showing town boundaries for:', towns);

  clearTownPolygons();
  clearAmenityMarkers();
  clearListingMarkers();

  const bounds = new mapboxgl.LngLatBounds();
  const colors = ['#10b981', '#3b82f6', '#f59e0b', '#ef4444', '#8b5cf6'];

  // Ensure map is fully loaded before adding sources
  const addBoundaries = () => {
    towns.forEach((town, index) => {
      if (!town.boundary || !town.boundary.coordinates) {
        console.warn('Town missing boundary:', town.town_name);
        return;
      }

      const sourceId = `town-${town.town_name.replace(/\s+/g, '-').toLowerCase()}-${Date.now()}-${index}`;
      const layerId = sourceId;
      const outlineId = `${layerId}-outline`;

      try {
        // Add source
        hdbMap.addSource(sourceId, {
          type: 'geojson',
          data: {
            type: 'Feature',
            geometry: town.boundary,
            properties: {
              name: town.town_name,
              region: town.region || 'Unknown',
              maturity: town.maturity || 'Unknown'
            }
          }
        });

        // Add fill layer
        hdbMap.addLayer({
          id: layerId,
          type: 'fill',
          source: sourceId,
          paint: {
            'fill-color': colors[index % colors.length],
            'fill-opacity': 0.3
          }
        });

        // Add outline layer
        hdbMap.addLayer({
          id: outlineId,
          type: 'line',
          source: sourceId,
          paint: {
            'line-color': colors[index % colors.length],
            'line-width': 3
          }
        });

        townPolygons.push(layerId);

        console.log(`Added town boundary for ${town.town_name}`);

        // Add marker at center
        if (town.center_lat && town.center_lng) {
          const el = document.createElement('div');
          el.className = 'town-marker';
          el.innerHTML = `<div style="background: white; padding: 8px 16px; border-radius: 8px; border: 2px solid ${colors[index % colors.length]}; font-weight: bold; font-size: 13px; color: #18181b; box-shadow: 0 2px 8px rgba(0,0,0,0.2); white-space: nowrap;">${town.town_name}</div>`;

          const marker = new mapboxgl.Marker(el)
            .setLngLat([town.center_lng, town.center_lat])
            .addTo(hdbMap);

          listingMarkers.push(marker); // Store for cleanup
        }

        // Extend bounds
        if (town.boundary.coordinates && town.boundary.coordinates[0]) {
          town.boundary.coordinates[0].forEach(coord => {
            bounds.extend(coord);
          });
        }
      } catch (error) {
        console.error(`Error adding boundary for ${town.town_name}:`, error);
      }
    });

    if (!bounds.isEmpty()) {
      setTimeout(() => {
        hdbMap.fitBounds(bounds, { padding: 50, maxZoom: 12, duration: 1000 });
      }, 100);
    }
  };

  // Check if map is loaded
  if (hdbMap.loaded()) {
    addBoundaries();
  } else {
    hdbMap.once('load', addBoundaries);
  }
}

function highlightComparedTownsOnMap(comparison) {
  if (!hdbMap || !Array.isArray(comparison) || comparison.length === 0) return;

  // Clear any existing markers/layers for town comparison
  clearCompareTownHighlights();

  const features = [];
  let bounds = null;

  // Helper: expand bounds using all coordinates from a Polygon / MultiPolygon
  const extendBoundsFromGeometry = (geometry) => {
    if (!geometry || !geometry.type || !geometry.coordinates) return;

    const extendCoord = (coord) => {
      if (!coord || coord.length < 2) return;
      const rawLng = coord[0];
      const rawLat = coord[1];

      const lng = typeof rawLng === "number" ? rawLng : parseFloat(rawLng);
      const lat = typeof rawLat === "number" ? rawLat : parseFloat(rawLat);

      if (!Number.isFinite(lng) || !Number.isFinite(lat)) return;

      if (!bounds) {
        bounds = new mapboxgl.LngLatBounds([lng, lat], [lng, lat]);
      } else {
        bounds.extend([lng, lat]);
      }
    };

    if (geometry.type === "Polygon") {
      (geometry.coordinates || []).forEach((ring) => {
        (ring || []).forEach(extendCoord);
      });
    } else if (geometry.type === "MultiPolygon") {
      (geometry.coordinates || []).forEach((poly) => {
        (poly || []).forEach((ring) => {
          (ring || []).forEach(extendCoord);
        });
      });
    }
  };

  comparison.forEach((town) => {
    if (!town) return;

    const townName = (town.town || "").toUpperCase().trim();

    let geomSource = null;
    if (town.boundary) {
      geomSource = town.boundary;
    } else if (town.geometry) {
      geomSource = town.geometry;
    }

    if (geomSource) {
      // Case A: FeatureCollection per town (as built in bootstrap)
      if (geomSource.type === "FeatureCollection" && Array.isArray(geomSource.features)) {
        geomSource.features.forEach((f) => {
          if (!f || !f.geometry) return;

          // Clone feature so we do not mutate original object
          const feat = {
            type: "Feature",
            geometry: f.geometry,
            properties: {
              ...(f.properties || {}),
              town: townName
            }
          };
          features.push(feat);
          extendBoundsFromGeometry(f.geometry);
        });
      }
      // Case B: single Geometry object
      else if (geomSource.type === "Polygon" || geomSource.type === "MultiPolygon") {
        const feat = {
          type: "Feature",
          geometry: geomSource,
          properties: {
            town: townName
          }
        };
        features.push(feat);
        extendBoundsFromGeometry(geomSource);
      }
    }

    // 2) Always add a marker at the town centre if we have one (for visual focus + popup)
    const centerLatRaw = town.center_lat;
    const centerLngRaw = town.center_lng;

    const centerLat = typeof centerLatRaw === "number" ? centerLatRaw : parseFloat(centerLatRaw);
    const centerLng = typeof centerLngRaw === "number" ? centerLngRaw : parseFloat(centerLngRaw);

    if (Number.isFinite(centerLat) && Number.isFinite(centerLng)) {
      const markerEl = document.createElement("div");
      markerEl.className = "compare-town-marker";
      markerEl.style.width = "14px";
      markerEl.style.height = "14px";
      markerEl.style.borderRadius = "9999px";
      markerEl.style.border = "2px solid #22c55e";
      markerEl.style.backgroundColor = "rgba(34, 197, 94, 0.2)";

      const popup = new mapboxgl.Popup({ offset: 12 }).setHTML(`
        <div style="font-size: 12px; font-weight: 600; color: #166534;">
          ${town.town || townName || "Selected town"}
        </div>
      `);

      const marker = new mapboxgl.Marker(markerEl)
        .setLngLat([centerLng, centerLat])
        .setPopup(popup)
        .addTo(hdbMap);

      compareTownMarkers.push(marker);

      // If we did not get any polygon geometry for this town, at least extend bounds with the centre
      if (!geomSource) {
        if (!bounds) {
          bounds = new mapboxgl.LngLatBounds([centerLng, centerLat], [centerLng, centerLat]);
        } else {
          bounds.extend([centerLng, centerLat]);
        }
      }
    }
  });

  // Add the GeoJSON source + fill + outline layers if we have any polygon features
  if (features.length > 0) {
    hdbMap.addSource("compare-towns-source", {
      type: "geojson",
      data: {
        type: "FeatureCollection",
        features: features
      }
    });

    // Fill the town polygons with a semi-transparent green highlight
    hdbMap.addLayer({
      id: "compare-towns-fill",
      type: "fill",
      source: "compare-towns-source",
      paint: {
        "fill-color": "#22c55e",
        "fill-opacity": 0.18
      }
    });

    // Draw a darker green outline around the highlighted towns
    hdbMap.addLayer({
      id: "compare-towns-outline",
      type: "line",
      source: "compare-towns-source",
      paint: {
        "line-color": "#15803d",
        "line-width": 2
      }
    });
  }

  // Finally, fit the map view to all collected bounds (polygons and/or centres)
  if (bounds) {
    hdbMap.fitBounds(bounds, {
      padding: { top: 40, bottom: 40, left: 360, right: 40 },
      maxZoom: 13,
      duration: 800
    });
  }
}

function showListingsOnMap(listings) {
  if (!hdbMap || !listings || listings.length === 0) return;

  // Clear any existing markers and polygon highlights before drawing new listings
  clearListingMarkers();
  clearAmenityMarkers();
  clearTownPolygons();
  clearCompareTownHighlights();

  const bounds = new mapboxgl.LngLatBounds();

  listings.forEach((listing) => {
    if (!listing.latitude || !listing.longitude) return;

    const lng = parseFloat(listing.longitude);
    const lat = parseFloat(listing.latitude);

    // Compute price (supports multiple possible fields) and approximate range if available
    const priceCandidate = [listing.price, listing.resale_price, listing.estimated_price].find(v => v !== undefined && v !== null && v !== '');
    const price = typeof priceCandidate === "number" ? priceCandidate : (priceCandidate ? parseFloat(priceCandidate) : null);
    const priceSourceMonth = listing.price_source_month || listing.resale_month || listing.estimated_month || null;
    const priceRange = getPriceRange(price);

    // Create custom marker
    const el = document.createElement("div");
    el.className = "listing-marker";
    el.innerHTML = `
      <div style="width: 32px; height: 32px; background: linear-gradient(135deg, #10b981, #059669); border: 3px solid white; border-radius: 50%; display: flex; align-items: center; justify-content: center; box-shadow: 0 2px 8px rgba(0,0,0,0.3); cursor: pointer;">
        <svg style="width: 18px; height: 18px; color: white;" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 12l9-9 9 9M5 10v10a1 1 0 001 1h4m4 0h4a1 1 0 001-1V10" />
        </svg>
      </div>
    `;

    const remarksText = listing.remarks || "No description";

    const marker = new mapboxgl.Marker(el)
      .setLngLat([lng, lat])
      .addTo(hdbMap);

    listingMarkers.push(marker);
    bounds.extend([lng, lat]);

    // When clicking the house icon marker, show price + nearby amenities
    el.addEventListener("click", (evt) => {
      evt.stopPropagation();
      if (!hdbMap) return;

      // Close any previously open listing popup so only one is visible
      if (currentListingPopup) {
        currentListingPopup.remove();
        currentListingPopup = null;
      }

      // Compute and show nearby amenities around this listing (~600m)
      const nearby = showNearbyAmenitiesOnMap(lat, lng, 600) || [];

      const amenitiesHtml = nearby.length === 0
        ? '<p style="font-size:11px; color:#9ca3af; margin-top:2px;">No amenities found within ~600m.</p>'
        : `
          <ul style="margin:4px 0 0; padding-left:16px; max-height:120px; overflow-y:auto;">
            ${nearby.map((f) => {
              const props = f.properties || {};
              const name = props.NAME || props.name || "Amenity";
              const klass = props.CLASS || props.amenity_type || "";
              return `<li style="font-size:11px; color:#4b5563; margin-bottom:2px;">• ${name}${klass ? ` <span style="color:#9ca3af;">(${klass})</span>` : ""}</li>`;
            }).join("")}
          </ul>
        `;

      const popupHtml = `
        <div style="min-width: 280px; max-width: 320px;">
          <div style="font-weight: 700; margin-bottom: 4px; color: #18181b; font-size: 15px;">
            🏠 Block ${listing.block}, ${listing.street}
          </div>
          <div style="font-size: 12px; color: #52525b; margin-bottom: 4px;">
            <span style="font-weight: 600; color: #059669;">${listing.town}</span> • ${listing.flat_type}
          </div>
          ${price ? `
          <div style="font-size: 13px; color: #16a34a; font-weight: 700; margin-bottom: 2px;">
            Price: $${Number(price).toLocaleString()}
          </div>
          ${priceSourceMonth ? `<div style="font-size: 10px; color: #6b7280; margin-bottom: 2px;">Source: HDB resale ${priceSourceMonth}</div>` : ``}
          ${priceRange ? `<div style="font-size: 11px; color: #4b5563; margin-bottom: 8px;">
            Approx. recent range: <span style="font-weight:600;">${priceRange.label}</span>
          </div>` : ``}
          ` : ``}
          <div style="font-size: 12px; color: #3f3f46; line-height: 1.5; margin-bottom: 8px; max-height: 120px; overflow-y: auto; padding-right: 4px; white-space: pre-line;">
            ${remarksText}
          </div>
          <div style="font-size: 11px; color: #71717a; border-top: 1px solid #e5e7eb; padding-top: 6px; margin-top: 6px;">
            📍 ${lat.toFixed(5)}, ${lng.toFixed(5)}
          </div>
          <div style="font-size: 11px; color: #6b7280; margin-top: 4px;">
            Nearby amenities (~600m):
            ${amenitiesHtml}
          </div>
        </div>
      `;

      const popup = new mapboxgl.Popup({ offset: 25, maxWidth: "320px" });

      // Ensure only one listing popup is open at any time
      popup.on("open", () => {
        if (currentListingPopup && currentListingPopup !== popup) {
          currentListingPopup.remove();
        }
        currentListingPopup = popup;
      });

      popup.on("close", () => {
        if (currentListingPopup === popup) {
          currentListingPopup = null;
        }
      });

      popup.setHTML(popupHtml);

      hdbMap.flyTo({
        center: [lng, lat],
        zoom: 16,
        duration: 1500
      });

      marker.setPopup(popup);
      marker.togglePopup();
    });
  });

  if (!bounds.isEmpty()) {
    hdbMap.fitBounds(bounds, { padding: 50, maxZoom: 14 });
  }
}

function updateAmenityStats(count) {
  const statsEl = $("#amenity-stats");
  if (statsEl) {
    statsEl.innerHTML = `
      <div class="col-span-2 p-4 bg-emerald-50 border border-emerald-300 rounded-lg">
        <div class="text-sm text-emerald-700 font-semibold mb-1">Total Amenities Loaded</div>
        <div class="text-3xl font-bold text-emerald-600">${count.toLocaleString()}</div>
        <div class="text-xs text-emerald-600 mt-1">Showing all markers on map</div>
      </div>
    `;
  }
}

// ========== API HELPERS ==========
async function getJSON(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`HTTP ${r.status}: ${r.statusText}`);
  return r.json();
}

async function postJSON(url, data) {
  const r = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data || {}),
  });
  if (!r.ok) throw new Error(`HTTP ${r.status}: ${r.statusText}`);
  return r.json();
}

async function deleteJSON(url) {
  const r = await fetch(url, { method: "DELETE" });
  if (!r.ok) throw new Error(`HTTP ${r.status}: ${r.statusText}`);
  return r.json();
}

// ========== UI HELPERS ==========
function showLoading(el, text = "Loading...") {
  if (!el) return;
  el.classList.remove("hidden");
  el.innerHTML = `
    <div class="flex items-center space-x-2">
      <div class="spinner"></div>
      <span>${text}</span>
    </div>
  `;
}

function hideLoading(el) {
  if (!el) return;
  el.classList.add("hidden");
}

function showError(el, message) {
  if (!el) return;
  el.innerHTML = `
    <div class="p-4 bg-red-900/20 border border-red-500/50 rounded-lg text-red-400 text-sm">
      <strong>Error:</strong> ${message}
    </div>
  `;
}

function renderTable(el, rows) {
  if (!el) return;
  
  if (!rows || !rows.length) {
    el.innerHTML = `<p class="text-sm text-zinc-600 text-center py-8">No results found.</p>`;
    return;
  }
  
  const cols = Object.keys(rows[0]);
  el.innerHTML = `
    <div class="overflow-x-auto">
      <table class="w-full text-sm">
        <thead class="text-left text-zinc-700 border-b-2 border-zinc-300 bg-slate-100">
          <tr>${cols.map(c => `<th class="py-3 px-4 font-semibold">${c.replace(/_/g, ' ').toUpperCase()}</th>`).join("")}</tr>
        </thead>
        <tbody class="divide-y divide-zinc-200">
          ${rows.map(r => `
            <tr class="hover:bg-slate-50 transition">
              ${cols.map(c => {
                let val = r[c];
                if (typeof val === 'number') {
                  if (c.includes('price') || c.includes('psm')) {
                    val = '$' + val.toLocaleString();
                  } else {
                    val = val.toLocaleString();
                  }
                }
                return `<td class="py-3 px-4 text-zinc-700">${val}</td>`;
              }).join("")}
            </tr>
          `).join("")}
        </tbody>
      </table>
    </div>
  `;
}

// ========== TAB SYSTEM ==========
function useTabs() {
  const tabs = $$(".ui-tab");
  const panels = $$(".ui-panel");
  
  tabs.forEach(btn => {
    btn.addEventListener("click", () => {
      tabs.forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      const id = btn.dataset.tab;
      panels.forEach(p => p.classList.add("hidden"));
      const panel = $(`#panel-${id}`);
      if (panel) {
        panel.classList.remove("hidden");
        panel.classList.add("animate-fade-in");
      }
    });
  });
}

// ========== CHART RENDERING ==========
function renderTrendChart(data) {
  const ctx = $("#trend-chart");
  if (!ctx) return;
  
  if (trendChart) {
    trendChart.destroy();
  }
  
  const labels = data.map(d => d.month);
  const medianData = data.map(d => d.median_psm);
  const avgData = data.map(d => d.avg_psm);
  
  trendChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: labels,
      datasets: [
        {
          label: 'Median $/sqm',
          data: medianData,
          borderColor: 'rgb(16, 185, 129)',
          backgroundColor: 'rgba(16, 185, 129, 0.1)',
          tension: 0.4,
          fill: true,
          pointRadius: 4,
          pointHoverRadius: 6,
        },
        {
          label: 'Average $/sqm',
          data: avgData,
          borderColor: 'rgb(59, 130, 246)',
          backgroundColor: 'rgba(59, 130, 246, 0.1)',
          tension: 0.4,
          fill: true,
          pointRadius: 4,
          pointHoverRadius: 6,
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: {
        mode: 'index',
        intersect: false,
      },
      plugins: {
        legend: {
          display: true,
          position: 'top',
          labels: {
            color: '#52525b',
            usePointStyle: true,
            padding: 15,
          }
        },
        tooltip: {
          backgroundColor: 'rgba(255, 255, 255, 0.95)',
          titleColor: '#18181b',
          bodyColor: '#3f3f46',
          borderColor: '#e4e4e7',
          borderWidth: 1,
          padding: 12,
          displayColors: true,
          callbacks: {
            label: function(context) {
              let label = context.dataset.label || '';
              if (label) {
                label += ': ';
              }
              if (context.parsed.y !== null) {
                label += '$' + context.parsed.y.toLocaleString();
              }
              return label;
            }
          }
        }
      },
      scales: {
        x: {
          grid: {
            color: 'rgba(228, 228, 231, 0.5)',
            drawBorder: false,
          },
          ticks: {
            color: '#71717a',
          }
        },
        y: {
          grid: {
            color: 'rgba(228, 228, 231, 0.5)',
            drawBorder: false,
          },
          ticks: {
            color: '#71717a',
            callback: function(value) {
              return '$' + value.toLocaleString();
            }
          }
        }
      }
    }
  });
}

// ========== PANEL 1: EXPLORE TRENDS ==========
async function setupTrendsPanel() {
  const btnSearch = $("#btn-search");
  if (!btnSearch) return;

  btnSearch.addEventListener("click", async () => {
    const trendState = $("#trend-state");
    const trendTable = $("#trend-table");
    const trendLoading = $("#trend-loading");
    
    showLoading(trendState, "Running SQL query with window functions...");
    if (trendLoading) trendLoading.classList.remove("hidden");
    
    try {
      const res = await postJSON("/api/search/trends", {
        town: $("#sel-town")?.value,
        flat_type: $("#sel-flat")?.value,
        start_month: $("#sel-start")?.value,
        end_month: $("#sel-end")?.value
      });
      
      if (res.ok && res.rows && res.rows.length > 0) {
        renderTrendChart(res.rows);
        renderTable(trendTable, res.rows);
      } else {
        if (trendTable) showError(trendTable, "No data returned for selected filters");
      }
    } catch (err) {
      if (trendTable) showError(trendTable, err.message);
      console.error("Trends query error:", err);
    } finally {
      hideLoading(trendState);
      if (trendLoading) trendLoading.classList.add("hidden");
    }
  });
}

// ========== PANEL 2: TRANSACTIONS ==========
async function setupTransactionsPanel() {
  const btnSearchTrans = $("#btn-search-trans");
  if (!btnSearchTrans) return;

  btnSearchTrans.addEventListener("click", async () => {
    const transList = $("#trans-list");
    const transCount = $("#trans-count");
    const transLoading = $("#trans-loading");
    
    showLoading(transLoading, "Loading transactions...");
    
    try {
      const res = await postJSON("/api/search/transactions", {
        town: $("#trans-town")?.value,
        flat_type: $("#trans-flat")?.value,
        limit: parseInt($("#trans-limit")?.value || 20)
      });
      
      if (res.ok && res.transactions) {
        if (transCount) transCount.textContent = `${res.count} results`;
        
        if (transList) {
          transList.innerHTML = res.transactions.map(t => `
            <div class="p-4 bg-slate-50 rounded-lg border border-zinc-300 hover:border-emerald-500 transition">
              <div class="flex items-start justify-between mb-2">
                <div>
                  <div class="font-semibold text-zinc-900">Block ${t.block}, ${t.street}</div>
                  <div class="text-xs text-zinc-600 mt-1">${t.storey} • ${t.floor_area} sqm • ${t.remaining_lease}</div>
                </div>
                <div class="text-right">
                  <div class="text-lg font-bold text-emerald-600">$${t.price.toLocaleString()}</div>
                  <div class="text-xs text-zinc-600">$${t.psm.toLocaleString()}/sqm</div>
                </div>
              </div>
              <div class="flex items-center justify-between text-xs text-zinc-500">
                <span>Lease from ${t.lease_start}</span>
                <span>${t.month}</span>
              </div>
            </div>
          `).join("");
        }
      } else {
        if (transList) transList.innerHTML = `<p class="text-center text-zinc-600 py-8">No transactions found</p>`;
      }
    } catch (err) {
      if (transList) showError(transList, err.message);
      console.error("Transactions query error:", err);
    } finally {
      hideLoading(transLoading);
    }
  });
}

// ========== PANEL 3: AFFORDABILITY ==========
async function setupAffordabilityPanel() {
  const btnAfford = $("#btn-afford");
  if (!btnAfford) return;

  btnAfford.addEventListener("click", async () => {
    const afResult = $("#af-result");
    if (!afResult) return;
    
    afResult.innerHTML = `
      <div class="flex items-center justify-center py-8">
        <div class="spinner"></div>
      </div>
    `;
    
    let hasChanged = false;
    
    try {
      const payload = {
        income: parseFloat($("#af-income")?.value) || 0,
        expenses: parseFloat($("#af-expenses")?.value) || 0,
        interest: parseFloat($("#af-interest")?.value) || 2.6,
        tenure_years: parseInt($("#af-tenure")?.value) || 25,
        down_payment_pct: parseFloat($("#af-downpayment")?.value) || 20,
      };
      
      // Compute a simple signature of the current calculator state
      const signature = JSON.stringify(payload);
      hasChanged = signature !== lastAffordSignature;
      
      // Only clear markers (and later reload houses) if user actually changed inputs
      if (hasChanged) {
        clearListingMarkers();
        clearAmenityMarkers();
        lastAffordSignature = signature;
      }
      
      const res = await postJSON("/api/affordability", payload);
      
      if (!res.ok) {
        showError(afResult, "Calculation failed");
        return;
      }
      
      const statusColor = res.affordable ? 'emerald' : 'red';
      const statusIcon = res.affordable ? 
        `<svg class="w-7 h-7" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"></path>
        </svg>` :
        `<svg class="w-7 h-7" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z"></path>
        </svg>`;
      
      afResult.innerHTML = `
        <div class="space-y-3">
          <div class="flex items-center space-x-3 p-4 bg-${statusColor}-50 border-2 border-${statusColor}-500 rounded-lg">
            <div class="text-${statusColor}-600 flex-shrink-0">${statusIcon}</div>
            <div class="flex-1 min-w-0">
              <div class="font-bold text-base text-${statusColor}-700">
                ${res.affordable ? 'Affordable!' : 'May Be Challenging'}
              </div>
              <div class="text-xs text-${statusColor}-600 font-medium">Based on 30% income threshold</div>
            </div>
          </div>
          
          <div class="grid grid-cols-2 gap-2">
            <div class="p-2.5 bg-slate-50 rounded-lg border border-zinc-300">
              <div class="text-[9px] text-zinc-600 font-semibold mb-1 uppercase tracking-wide">Max Property</div>
              <div class="text-base font-bold text-emerald-600 leading-tight">${Math.round(res.max_property_value).toLocaleString()}</div>
            </div>
            
            <div class="p-2.5 bg-slate-50 rounded-lg border border-zinc-300">
              <div class="text-[9px] text-zinc-600 font-semibold mb-1 uppercase tracking-wide">Max Loan</div>
              <div class="text-base font-bold text-blue-600 leading-tight">${Math.round(res.max_loan_amount).toLocaleString()}</div>
            </div>
            
            <div class="p-2.5 bg-slate-50 rounded-lg border border-zinc-300">
              <div class="text-[9px] text-zinc-600 font-semibold mb-1 uppercase tracking-wide">Monthly Pay</div>
              <div class="text-sm font-bold text-zinc-900 leading-tight">${Math.round(res.max_monthly_payment).toLocaleString()}</div>
            </div>
            
            <div class="p-2.5 bg-slate-50 rounded-lg border border-zinc-300">
              <div class="text-[9px] text-zinc-600 font-semibold mb-1 uppercase tracking-wide">Price/sqm</div>
              <div class="text-sm font-bold text-zinc-900 leading-tight">${Math.round(res.max_psm).toLocaleString()}</div>
            </div>
          </div>
          
          <div class="p-3 bg-slate-100 rounded-lg border border-zinc-300">
            <div class="text-[10px] text-zinc-700 font-semibold mb-1.5 uppercase tracking-wide">Calculation Details</div>
            <div class="text-xs text-zinc-700 space-y-0.5 leading-relaxed">
              <p>• Down payment: <span class="font-bold text-emerald-600">${Math.round(res.down_payment_required).toLocaleString()}</span></p>
              <p>• Interest: <span class="font-semibold">${payload.interest}%</span> over <span class="font-semibold">${payload.tenure_years} years</span></p>
              <p>• Down payment %: <span class="font-semibold">${payload.down_payment_pct}%</span></p>
            </div>
          </div>
        </div>
      `;

      // After showing the calculation result, also show affordable listings on the map
      // Only reload map markers if inputs changed
      if (hasChanged) {
        try {
          const maxValue = typeof res.max_property_value === "number"
            ? res.max_property_value
            : (res.max_property_value ? parseFloat(res.max_property_value) : NaN);

          if (!Number.isNaN(maxValue) && maxValue > 0) {
            await loadAffordableListingsOnMap(maxValue);
          } else {
            console.warn("Affordability result did not contain a usable max_property_value; skipping map update.");
          }
        } catch (mapErr) {
          console.warn("Error while trying to show affordable listings on map:", mapErr);
        }
      }
    } catch (err) {
      showError(afResult, err.message);
      console.error("Affordability calculation error:", err);
    }
  });
}

// Helper: Show affordable listings on map, filtered by max property value and current search filters
async function loadAffordableListingsOnMap(maxPropertyValue, options = {}) {
  if (!hdbMap) {
    console.warn("Map not initialized; cannot show affordable listings.");
    return;
  }

  if (!maxPropertyValue || Number.isNaN(maxPropertyValue)) {
    console.warn("Invalid maxPropertyValue passed to loadAffordableListingsOnMap:", maxPropertyValue);
    return;
  }

  try {
    // Optionally respect town/flat-type filters from the Search Listings panel if present
    const townFilterEl = $("#listing-town-filter");
    const flatTypeFilterEl = $("#listing-flat-type-filter");

    const payload = {
      query: "",
      town: townFilterEl ? (townFilterEl.value || null) : (options.town || null),
      flat_type: flatTypeFilterEl ? (flatTypeFilterEl.value || null) : (options.flat_type || options.flatType || null),
      limit: options.limit || 200
    };

    const res = await postJSON("/api/listings/search", payload);

    if (!res || !res.ok || !Array.isArray(res.results)) {
      console.warn("Could not load listings for affordability map view:", res && res.error);
      return;
    }

    const allListings = res.results;

    const affordableListings = allListings.filter((listing) => {
      const candidate =
        listing.price ??
        listing.resale_price ??
        listing.estimated_price;

      const price =
        typeof candidate === "number"
          ? candidate
          : candidate
          ? parseFloat(candidate)
          : NaN;

      return price && !Number.isNaN(price) && price <= maxPropertyValue;
    });

    if (!affordableListings.length) {
      console.info("No listings found under the calculated affordability limit.");
    }

    // Reuse existing logic to clear markers and draw listings
    showListingsOnMap(affordableListings);
  } catch (err) {
    console.error("Error in loadAffordableListingsOnMap:", err);
  }
}

// ========== PANEL 4: TOWN COMPARISON ==========
async function setupComparePanel() {
  const btnCompare = $("#btn-compare");
  if (!btnCompare) return;

  btnCompare.addEventListener("click", async () => {
    const results = $("#compare-results");
    if (!results) return;
    
    results.innerHTML = `
      <div class="col-span-3 flex items-center justify-center py-12">
        <div class="spinner"></div>
      </div>
    `;
    
    try {
      const towns = [
        $("#comp-town1")?.value,
        $("#comp-town2")?.value,
        $("#comp-town3")?.value
      ].filter(t => t);
      
      const res = await postJSON("/api/compare/towns", {
        towns: towns,
        flat_type: $("#sel-flat")?.value || "4 ROOM"
      });
      
      if (res.ok && res.comparison) {
        results.innerHTML = res.comparison.map(town => `
          <div class="p-6 bg-gradient-to-br from-white to-slate-50 rounded-xl border-2 border-zinc-200 hover:border-emerald-400 card-hover shadow-sm">
            <h3 class="text-2xl font-bold mb-1 bg-gradient-to-r from-emerald-600 to-emerald-500 bg-clip-text text-transparent">${town.town}</h3>
            ${town.region ? `<p class="text-xs text-zinc-500 mb-4 font-medium uppercase tracking-wide">${town.region} • ${town.maturity || 'N/A'}</p>` : ''}
            
            <div class="space-y-3">
              <div class="flex justify-between items-center p-2 bg-white rounded-lg">
                <span class="text-xs text-zinc-600 font-semibold uppercase tracking-wide">Median $/sqm</span>
                <span class="font-extrabold text-xl bg-gradient-to-r from-blue-600 to-blue-500 bg-clip-text text-transparent">${town.median_psm.toLocaleString()}</span>
              </div>
              
              <div class="flex justify-between items-center p-2 bg-white rounded-lg">
                <span class="text-xs text-zinc-600 font-semibold uppercase tracking-wide">Avg Price</span>
                <span class="font-bold text-lg text-purple-600">${town.avg_price.toLocaleString()}</span>
              </div>
              
              <div class="flex justify-between items-center p-2 bg-white rounded-lg">
                <span class="text-xs text-zinc-600 font-semibold uppercase tracking-wide">Transactions</span>
                <span class="font-bold text-lg text-orange-600">${town.transactions.toLocaleString()}</span>
              </div>
              
              ${town.characteristics && town.characteristics.length > 0 ? `
                <div class="pt-3 border-t-2 border-zinc-200">
                  <div class="text-[10px] text-zinc-600 font-bold mb-2 uppercase tracking-wider">Characteristics</div>
                  <div class="flex flex-wrap gap-1.5">
                    ${town.characteristics.slice(0, 4).map(c => `
                      <span class="px-2.5 py-1 text-[10px] font-semibold bg-gradient-to-r from-emerald-100 to-emerald-50 text-emerald-700 rounded-full border border-emerald-200">${c}</span>
                    `).join('')}
                  </div>
                </div>
              ` : ''}
              
              <div class="pt-3 border-t-2 border-zinc-200">
                <div class="text-[10px] text-zinc-600 font-bold mb-2 uppercase tracking-wider">Affordability Score</div>
                <div class="flex items-center space-x-2">
                  <div class="flex-1 h-3 bg-zinc-200 rounded-full overflow-hidden shadow-inner">
                    <div class="h-full bg-gradient-to-r from-emerald-600 via-emerald-500 to-emerald-400 rounded-full transition-all duration-500" 
                         style="width: ${town.affordability_score * 10}%"></div>
                  </div>
                  <span class="font-extrabold text-lg bg-gradient-to-r from-emerald-600 to-emerald-500 bg-clip-text text-transparent">${town.affordability_score}/10</span>
                </div>
              </div>
            </div>
          </div>
        `).join("");

        // Highlight compared towns on the map using geometry/center from API
        highlightComparedTownsOnMap(res.comparison);
      } else {
        results.innerHTML = `<p class="col-span-3 text-center text-zinc-600 py-8">No comparison data available</p>`;
      }
    } catch (err) {
      results.innerHTML = `<div class="col-span-3 p-4 bg-red-900/20 border border-red-500/50 rounded-lg text-red-400">${err.message}</div>`;
      console.error("Town comparison error:", err);
    }
  });
}

// ========== PANEL 5: LISTING REMARKS SEARCH (MongoDB Text Search) ==========
async function setupListingsPanel() {
  const btnSearch = $("#btn-search-listings");
  if (!btnSearch) return;

  btnSearch.addEventListener("click", async () => {
    const resultsDiv = $("#listing-results");
    const countDiv = $("#listing-count");
    const loadingDiv = $("#listing-loading");
    
    const query = $("#listing-search-query")?.value.trim() || "";
    const town = $("#listing-town-filter")?.value;
    const flatType = $("#listing-flat-type-filter")?.value;
    
    if (!query) {
      if (resultsDiv) resultsDiv.innerHTML = `<p class="text-center text-zinc-600 py-8">Please enter search keywords</p>`;
      return;
    }
    
    showLoading(loadingDiv, "Searching listings...");
    
    try {
      const res = await postJSON("/api/listings/search", {
        query: query,
        town: town || null,
        flat_type: flatType || null,
        limit: 20
      });
      
      if (res.ok && res.results) {
        if (countDiv) countDiv.textContent = `${res.count} results`;
        
        // Show listings on map
        if (res.results.length > 0) {
          showListingsOnMap(res.results);
        }
        
        if (res.count === 0) {
          if (resultsDiv) resultsDiv.innerHTML = `<p class="text-center text-zinc-600 py-8">No listings found matching "${query}"</p>`;
        } else {
          if (resultsDiv) {
            resultsDiv.innerHTML = res.results.map(listing => {
              let remarksPreview = listing.remarks || 'No description';
              // if (remarksPreview.length > 250) {
              //   remarksPreview = remarksPreview.substring(0, 250) + '...';
              // }
              
              return `
                <div class="p-4 bg-white rounded-lg border border-zinc-300 hover:border-emerald-500 transition cursor-pointer listing-card"
                      data-lat="${listing.latitude}"
                      data-lng="${listing.longitude}"
                      data-town="${listing.town}"
                      data-flat-type="${listing.flat_type}"
                      data-block="${listing.block}"
                      data-street="${listing.street}"
                      data-price="${(listing.price ?? listing.resale_price ?? listing.estimated_price) || ''}"
                      data-price-source-month="${listing.price_source_month ?? listing.resale_month ?? listing.estimated_month ?? ''}"
                      data-remarks="${(remarksPreview || '').replace(/"/g, '&quot;')}">
                  <div class="flex items-start justify-between mb-2">
                    <div class="flex-1">
                      <div class="font-semibold text-zinc-900">🏠 Block ${listing.block}, ${listing.street}</div>
                      <div class="text-xs text-zinc-600 mt-1">${listing.town} • ${listing.flat_type}</div>
                    </div>
                    ${listing.score ? `
                      <div class="px-2 py-1 text-xs bg-emerald-100 text-emerald-700 rounded-full font-medium">
                        Match: ${Math.round(listing.score * 100)}%
                      </div>
                    ` : ''}
                  </div>
                  <p class="text-sm text-zinc-700 leading-relaxed">${remarksPreview}</p>
                  <div class="mt-2 text-xs text-zinc-500 flex items-center justify-between">
                    <span>Posted: ${new Date(listing.created_date).toLocaleDateString()}</span>
                    ${listing.latitude && listing.longitude ? `
                      <span class="text-emerald-600 font-medium">📍 Click to view on map</span>
                    ` : ''}
                  </div>
                </div>
              `;
            }).join('');
            
            // Add click handlers to zoom to specific listing
            resultsDiv.querySelectorAll('.listing-card').forEach((card, index) => {
              card.dataset.index = index;

              card.addEventListener('click', () => {
                const lat = parseFloat(card.dataset.lat);
                const lng = parseFloat(card.dataset.lng);

                if (!lat || !lng || !hdbMap || !listingMarkers[index]) {
                  return;
                }

                // Close any previously open listing popup so only one is visible
                if (currentListingPopup) {
                  currentListingPopup.remove();
                  currentListingPopup = null;
                }

                const town = card.dataset.town || 'Unknown town';
                const flatType = card.dataset.flatType || 'Flat';
                const block = card.dataset.block || '';
                const street = card.dataset.street || '';
                const priceRaw = card.dataset.price || '';
                const priceSourceMonth = card.dataset.priceSourceMonth || '';
                const remarks = card.dataset.remarks || '';

                const price = priceRaw ? parseFloat(priceRaw) : null;
                const priceRange = getPriceRange(price);

                // Compute and show nearby amenities around this listing (~600m)
                const nearby = showNearbyAmenitiesOnMap(lat, lng, 600) || [];

                const amenitiesHtml = nearby.length === 0
                  ? '<p style="font-size:11px; color:#9ca3af; margin-top:2px;">No amenities found within ~600m.</p>'
                  : `
                    <ul style="margin:4px 0 0; padding-left:16px; max-height:120px; overflow-y:auto;">
                      ${nearby.map((f) => {
                        const props = f.properties || {};
                        const name = props.NAME || props.name || 'Amenity';
                        const klass = props.CLASS || props.amenity_type || '';
                        return `<li style="font-size:11px; color:#4b5563; margin-bottom:2px;">• ${name}${klass ? ` <span style="color:#9ca3af;">(${klass})</span>` : ''}</li>`;
                      }).join('')}
                    </ul>
                  `;

                const popupHtml = `
                  <div style="min-width: 280px; max-width: 320px;">
                    <div style="font-weight: 700; margin-bottom: 4px; color: #18181b; font-size: 15px;">
                      🏠 Block ${block}, ${street}
                    </div>
                    <div style="font-size: 12px; color: #52525b; margin-bottom: 4px;">
                      <span style="font-weight: 600; color: #059669;">${town}</span> • ${flatType}
                    </div>
                    ${price ? `
                    <div style="font-size: 13px; color: #16a34a; font-weight: 700; margin-bottom: 2px;">
                      Price: $${Number(price).toLocaleString()}
                    </div>
                    ${priceSourceMonth ? `<div style="font-size: 10px; color: #6b7280; margin-bottom: 2px;">Source: HDB resale ${priceSourceMonth}</div>` : ``}
                    ${priceRange ? `<div style="font-size: 11px; color: #4b5563; margin-bottom: 8px;">
                      Approx. recent range: <span style="font-weight:600;">${priceRange.label}</span>
                    </div>` : ``}
                    ` : ``}
                    ${remarks ? `<div style="font-size: 12px; color: #3f3f46; line-height: 1.5; margin-bottom: 8px; max-height: 120px; overflow-y: auto; padding-right: 4px; white-space: pre-line;">${remarks}</div>` : ''}
                    <div style="font-size: 11px; color: #71717a; border-top: 1px solid #e5e7eb; padding-top: 6px; margin-top: 6px;">
                      📍 ${lat.toFixed(5)}, ${lng.toFixed(5)}
                    </div>
                    <div style="font-size: 11px; color: #6b7280; margin-top: 4px;">
                      Nearby amenities (~600m):
                      ${amenitiesHtml}
                    </div>
                  </div>
                `;

                hdbMap.flyTo({
                  center: [lng, lat],
                  zoom: 16,
                  duration: 1500
                });

                const marker = listingMarkers[index];
                if (marker) {
                  const popup = new mapboxgl.Popup({ offset: 25, maxWidth: '320px' });
                  popup.on('open', () => {
                    if (currentListingPopup && currentListingPopup !== popup) {
                      currentListingPopup.remove();
                    }
                    currentListingPopup = popup;
                  });

                  popup.on('close', () => {
                    if (currentListingPopup === popup) {
                      currentListingPopup = null;
                    }
                  });

                  popup.setHTML(popupHtml);
                  marker.setPopup(popup);
                  marker.togglePopup();
                }
              });
            });
          }
        }
      } else {
        if (resultsDiv) showError(resultsDiv, "Search failed");
      }
    } catch (err) {
      if (resultsDiv) showError(resultsDiv, err.message);
      console.error("Listing search error:", err);
    } finally {
      hideLoading(loadingDiv);
    }
  });
  
  // Allow Enter key to search
  const searchInput = $("#listing-search-query");
  if (searchInput) {
    searchInput.addEventListener("keypress", (e) => {
      if (e.key === "Enter") {
        btnSearch.click();
      }
    });
  }
}

// ========== PANEL 6: AMENITIES ==========
async function setupAmenitiesPanel() {
  const classSelect = $("#amenity-class");
  const loadBtn = $("#btn-amenity-stats");

  if (!loadBtn) return;

  loadBtn.addEventListener("click", async () => {
    const amenityLoading = $("#amenity-loading");
    
    try {
      if (amenityLoading) {
        amenityLoading.classList.remove("hidden");
      }

      const amenityClass = classSelect ? classSelect.value : "";
      const params = new URLSearchParams();
      if (amenityClass) {
        params.set("class", amenityClass);
      }

      const queryString = params.toString() ? `?${params.toString()}` : "";
      const res = await fetch(`/api/amenities${queryString}`);

      if (!res.ok) {
        console.error("Failed to fetch amenities:", res.statusText);
        return;
      }

      const geojson = await res.json();
      console.log("Amenities GeoJSON:", geojson);
      showAmenitiesOnMap(geojson);
    } catch (err) {
      console.error("Error loading amenities:", err);
    } finally {
      if (amenityLoading) {
        amenityLoading.classList.add("hidden");
      }
    }
  });
}

// ========== BOOTSTRAP ==========
async function bootstrap() {
  console.log("🚀 Initializing HDB HomeFinder DB...");
  initMapbox();
  useTabs();
  
  try {
    const meta = await getJSON("/api/meta");
    // Preload all amenities for nearby-search around listings (no markers yet)
    try {
      const amenityClasses = ["MRT_STATION", "SCHOOL", "CLINIC", "SUPERMARKET", "PARK"];
      const mergedFeatures = [];

      for (const cls of amenityClasses) {
        try {
          const data = await getJSON(`/api/amenities?class=${encodeURIComponent(cls)}`);
          if (data && Array.isArray(data.features)) {
            mergedFeatures.push(...data.features);
          }
        } catch (classErr) {
          console.warn(`Could not preload amenities for class ${cls}:`, classErr);
        }
      }

      amenitiesData = {
        type: "FeatureCollection",
        features: mergedFeatures
      };

      console.log(
        "Preloaded amenities for proximity search (all classes):",
        amenitiesData.features.length
      );
    } catch (amenityErr) {
      console.warn(
        "Could not preload amenities for proximity search; nearby amenities in listing popups may be unavailable.",
        amenityErr
      );
    }

    
    // Populate town selects
    const townSelects = ["#sel-town", "#trans-town", "#amenity-town", "#comp-town1", "#comp-town2", "#comp-town3", "#listing-town-filter"];
    townSelects.forEach(sel => {
      const el = $(sel);
      if (el && meta.towns) {
        el.innerHTML = '<option value="">All Towns</option>' + meta.towns.map(t => `<option value="${t}">${t}</option>`).join("");
      }
    });
    
    // Populate flat type selects
    const flatSelects = ["#sel-flat", "#trans-flat", "#listing-flat-type-filter"];
    flatSelects.forEach(sel => {
      const el = $(sel);
      if (el && meta.flat_types) {
        el.innerHTML = '<option value="">All Types</option>' + meta.flat_types.map(t => `<option value="${t}">${t}</option>`).join("");
      }
    });
    
    // Populate month selects (reversed for chronological order with earliest first)
    const startSel = $("#sel-start");
    const endSel = $("#sel-end");
    if (startSel && endSel && meta.months) {
      const monthsHTML = meta.months.map(m => `<option value="${m}">${m}</option>`).join("");
      startSel.innerHTML = monthsHTML;
      endSel.innerHTML = monthsHTML;
      if (meta.months.length > 0) {
        // Set start to earliest (last in reversed array) and end to most recent (first in reversed array)
        startSel.value = meta.months[meta.months.length - 1];
        endSel.value = meta.months[0];
      }
    }
    
    // Setup all panels
    await setupTrendsPanel();
    await setupTransactionsPanel();
    await setupAffordabilityPanel();
    await setupComparePanel();
    await setupListingsPanel();
    await setupAmenitiesPanel();
    
    console.log("Application ready!");
  } catch (err) {
    console.error("Bootstrap error:", err);
    alert("Failed to initialize application: " + err.message);
  }
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', bootstrap);
} else {
  bootstrap();
}