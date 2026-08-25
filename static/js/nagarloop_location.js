/**
 * NagarLoop — Google-Maps-like Location & Address Picker
 * 
 * Features:
 * 1. Single Source of Truth: Synchronized latitude, longitude, and readable address.
 * 2. Backend-controlled Geocoding & Suggestions (/api/location/search and /api/location/reverse) with caching.
 * 3. Stale request protection & 350ms debounce for suggestions dropdown.
 * 4. Single draggable marker (L.marker with draggable: true).
 * 5. Intentional placement: Zero random locations on init. If no initial coords, shows Gujarat wide view without a marker until user searches, uses GPS, or clicks map.
 * 6. Existing location preserved on opening/closing.
 * 7. Manual address refinement without losing coordinates.
 * 8. GPS button ([ Use My Current Location ]) on explicit user tap.
 * 9. Clear [ Confirm Location ] and [ Refine / Change Location ] flow.
 */

class NagarLoopLocationPicker {
    constructor(options) {
        this.mapElementId = options.mapElementId || 'citizen-booking-map';
        this.latInputId = options.latInputId || 'form-lat';
        this.lngInputId = options.lngInputId || 'form-lng';
        this.addressInputId = options.addressInputId || 'form-address';
        this.confirmAddressId = options.confirmAddressId || 'location-confirmed-address';
        this.confirmCoordsId = options.confirmCoordsId || 'location-confirmed-coords';
        this.statusMsgId = options.statusMsgId || 'location-status-msg';
        this.dropdownContainerId = options.dropdownContainerId || (this.addressInputId + '-suggestions');
        this.collapsibleWrapperId = options.collapsibleWrapperId || 'map-collapsible-wrapper';
        this.confirmLocationBtnId = options.confirmLocationBtnId || 'btn-confirm-location';
        this.refineLocationBtnId = options.refineLocationBtnId || 'btn-refine-location';
        this.confirmedCardId = options.confirmedCardId || 'location-confirmed-card';

        // Initial coordinates (if provided)
        this.initialLat = (options.initialLat && !isNaN(parseFloat(options.initialLat))) ? parseFloat(options.initialLat) : null;
        this.initialLng = (options.initialLng && !isNaN(parseFloat(options.initialLng))) ? parseFloat(options.initialLng) : null;
        this.initialAddress = options.initialAddress || '';

        // Gujarat geographical center
        this.gujaratCenter = [22.3094, 72.1362];
        this.defaultZoom = (this.initialLat && this.initialLng) ? 16 : 7;

        this.map = null;
        this.marker = null;
        this.debounceTimer = null;
        this.currentRequestId = 0;
        this.activeAbortController = null;
        this.isManuallyEdited = false;

        this.init();
    }

    init() {
        const mapContainer = document.getElementById(this.mapElementId);
        if (!mapContainer) return;

        // Check if map already initialized on this DOM element
        if (mapContainer._leaflet_id && this.map) {
            this.map.invalidateSize();
            return;
        }

        const startCenter = (this.initialLat && this.initialLng) 
            ? [this.initialLat, this.initialLng] 
            : this.gujaratCenter;

        // Initialize Leaflet Map
        this.map = L.map(this.mapElementId, {
            center: startCenter,
            zoom: this.defaultZoom,
            minZoom: 6,
            maxZoom: 19
        });

        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
            maxZoom: 19
        }).addTo(this.map);

        // If valid initial coordinates exist, place initial marker
        if (this.initialLat && this.initialLng) {
            this.setMarkerLocation(this.initialLat, this.initialLng, false, false);
            if (this.initialAddress) {
                this.setAddressText(this.initialAddress, false);
            } else {
                this.reverseGeocode(this.initialLat, this.initialLng);
            }
            this.setStatusMessage("📍 Location selected. Drag pin to fine-tune exact doorstep.");
        } else {
            this.setStatusMessage("Search for your area, tap 'GPS', or click on the map to set pickup point.");
        }

        // Map Click Listener
        this.map.on('click', (e) => {
            const { lat, lng } = e.latlng;
            this.setMarkerLocation(lat, lng, true, false);
        });

        // Setup Autocomplete & Suggestions on Address / Search Input
        this.setupAddressAutocomplete();

        // Setup Confirm & Refine Location Controls
        this.setupConfirmControls();
    }

    // 1. Single Draggable Marker Placement
    setMarkerLocation(lat, lng, doReverseGeocode = true, flyTo = true) {
        const latNum = parseFloat(lat);
        const lngNum = parseFloat(lng);

        if (isNaN(latNum) || isNaN(lngNum)) return;

        if (!this.marker) {
            this.marker = L.marker([latNum, lngNum], {
                draggable: true,
                autoPan: true
            }).addTo(this.map);

            this.marker.on('dragend', (e) => {
                const pos = e.target.getLatLng();
                this.updateCoordinates(pos.lat, pos.lng);
                this.reverseGeocode(pos.lat, pos.lng);
            });
        } else {
            this.marker.setLatLng([latNum, lngNum]);
        }

        this.marker.bindPopup("<b>📍 Exact Pickup Point</b><br><small>Drag pin to fine-tune collection point</small>").openPopup();

        this.updateCoordinates(latNum, lngNum);

        if (flyTo && this.map) {
            const currentZoom = this.map.getZoom();
            const targetZoom = currentZoom < 15 ? 16 : currentZoom;
            this.map.flyTo([latNum, lngNum], targetZoom, { animate: true, duration: 0.8 });
        }

        if (doReverseGeocode) {
            this.reverseGeocode(latNum, lngNum);
        }

        this.setStatusMessage("📍 Exact pickup location locked. Drag pin to adjust.");
    }

    // 2. Setup Address Search Suggestions
    setupAddressAutocomplete() {
        const addrInput = document.getElementById(this.addressInputId);
        if (!addrInput) return;

        let wrapper = addrInput.closest('.nl-address-wrapper');
        if (!wrapper) {
            wrapper = document.createElement('div');
            wrapper.className = 'nl-address-wrapper';
            addrInput.parentNode.insertBefore(wrapper, addrInput);
            wrapper.appendChild(addrInput);
        }

        let dropdown = document.getElementById(this.dropdownContainerId);
        if (!dropdown) {
            dropdown = document.createElement('div');
            dropdown.id = this.dropdownContainerId;
            dropdown.className = 'nl-suggestions-dropdown';
            wrapper.appendChild(dropdown);
        }

        // Track manual typing vs suggestion selection
        addrInput.addEventListener('input', (e) => {
            this.isManuallyEdited = true;
            this.syncConfirmationUI();
            const val = e.target.value.trim();

            if (this.debounceTimer) clearTimeout(this.debounceTimer);

            if (val.length < 3) {
                this.hideDropdown();
                return;
            }

            this.debounceTimer = setTimeout(() => {
                this.fetchAddressSuggestions(val);
            }, 350);
        });

        // Close dropdown when clicked outside
        document.addEventListener('click', (e) => {
            if (!wrapper.contains(e.target)) {
                this.hideDropdown();
            }
        });

        // Keyboard navigation
        addrInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                const dropdown = document.getElementById(this.dropdownContainerId);
                const firstItem = dropdown ? dropdown.querySelector('.nl-suggestion-item') : null;
                if (firstItem) {
                    firstItem.click();
                } else {
                    this.searchLocation(addrInput.value);
                }
            } else if (e.key === 'Escape') {
                this.hideDropdown();
            }
        });
    }

    // 3. Fetch Suggestions via Backend API with Stale Request Protection
    fetchAddressSuggestions(query) {
        const dropdown = document.getElementById(this.dropdownContainerId);
        if (!dropdown) return;

        if (this.activeAbortController) {
            this.activeAbortController.abort();
        }
        this.activeAbortController = new AbortController();

        this.currentRequestId += 1;
        const reqId = this.currentRequestId;

        dropdown.innerHTML = `<div class="p-2 text-muted small"><i class="fa-solid fa-spinner fa-spin me-1 text-success"></i> Finding matching locations in Gujarat...</div>`;
        dropdown.style.display = 'block';

        fetch(`/api/location/search?q=${encodeURIComponent(query)}&request_id=${reqId}`, {
            signal: this.activeAbortController.signal
        })
        .then(res => res.json())
        .then(data => {
            // Ignore stale requests
            if (data.request_id && parseInt(data.request_id) !== this.currentRequestId) {
                return;
            }

            const results = (data && data.results) ? data.results : [];
            if (results.length === 0) {
                dropdown.innerHTML = `<div class="p-2 text-muted small"><i class="fa-solid fa-circle-info me-1"></i> No exact matches found for "${query}". You can continue typing or click on the map.</div>`;
                return;
            }

            dropdown.innerHTML = '';
            results.forEach(item => {
                const row = document.createElement('div');
                row.className = 'nl-suggestion-item';
                row.innerHTML = `
                    <i class="fa-solid fa-location-dot sugg-icon"></i>
                    <div>
                        <div class="sugg-title">${item.title}</div>
                        <div class="sugg-sub">${item.subtitle}</div>
                    </div>
                `;
                row.addEventListener('click', () => {
                    this.selectSuggestion(item);
                });
                dropdown.appendChild(row);
            });
        })
        .catch(err => {
            if (err.name !== 'AbortError') {
                dropdown.innerHTML = `<div class="p-2 text-muted small">Location search temporarily unavailable. You can click on the map directly.</div>`;
            }
        });
    }

    // 4. Select Suggestion from Search
    selectSuggestion(item) {
        const lat = parseFloat(item.lat);
        const lng = parseFloat(item.lng || item.lon);

        this.isManuallyEdited = false;
        const cleanAddress = item.display_name || `${item.title}, ${item.subtitle}`;
        this.setAddressText(cleanAddress, false);

        this.setMarkerLocation(lat, lng, false, true);
        this.hideDropdown();
        this.setStatusMessage(`📍 Location selected: ${item.title}. Drag pin to fine-tune exact doorstep.`);
    }

    hideDropdown() {
        const dropdown = document.getElementById(this.dropdownContainerId);
        if (dropdown) dropdown.style.display = 'none';
    }

    // 5. Update Hidden Form Inputs
    updateCoordinates(lat, lng) {
        const latInput = document.getElementById(this.latInputId);
        const lngInput = document.getElementById(this.lngInputId);
        if (latInput) latInput.value = parseFloat(lat).toFixed(6);
        if (lngInput) lngInput.value = parseFloat(lng).toFixed(6);
        this.syncConfirmationUI();
    }

    // 6. Set Address Text
    setAddressText(addr, isManual = false) {
        const addrInput = document.getElementById(this.addressInputId);
        if (addrInput) {
            addrInput.value = addr;
        }
        if (!isManual) {
            this.isManuallyEdited = false;
        }
        this.syncConfirmationUI();
    }

    // 7. Synchronize Live Review Card
    syncConfirmationUI() {
        const latInput = document.getElementById(this.latInputId);
        const lngInput = document.getElementById(this.lngInputId);
        const addrInput = document.getElementById(this.addressInputId);

        const lat = latInput ? latInput.value : '';
        const lng = lngInput ? lngInput.value : '';
        const addr = addrInput ? (addrInput.value.trim() || 'Address not specified') : 'Address not specified';

        const confAddr = document.getElementById(this.confirmAddressId);
        const confCoords = document.getElementById(this.confirmCoordsId);

        if (confAddr) confAddr.innerText = addr;
        if (confCoords) confCoords.innerText = (lat && lng) ? `${lat}, ${lng}` : 'Pending selection';
    }

    setStatusMessage(msg, isError = false) {
        const el = document.getElementById(this.statusMsgId);
        if (!el) return;
        el.innerText = msg;
        el.className = isError ? 'small text-danger fw-bold mt-1 d-block' : 'small text-muted mt-1 d-block';
    }

    // 8. Browser GPS Geolocation
    useGPSLocation() {
        this.setStatusMessage("Requesting GPS device location...");
        if (!navigator.geolocation) {
            this.setStatusMessage("Location permission denied. Search for your location or select it on the map.", true);
            return;
        }

        navigator.geolocation.getCurrentPosition(
            (pos) => {
                const lat = pos.coords.latitude;
                const lng = pos.coords.longitude;
                this.setMarkerLocation(lat, lng, true, true);
                this.setStatusMessage("📍 GPS location locked. Drag pin to fine-tune exact doorstep.");
            },
            (err) => {
                this.setStatusMessage("Location permission denied. Search for your location or select it on the map.", true);
            },
            { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 }
        );
    }

    // 9. Reverse Geocoding (/api/location/reverse)
    reverseGeocode(lat, lng) {
        this.setStatusMessage("Detecting street address...");
        fetch(`/api/location/reverse?lat=${lat}&lng=${lng}`)
            .then(res => res.json())
            .then(data => {
                if (data && data.success && data.address) {
                    if (!this.isManuallyEdited) {
                        this.setAddressText(data.address, false);
                    }
                    this.setStatusMessage("📍 Address detected. Drag pin or edit address details if needed.");
                } else {
                    this.setStatusMessage("📍 Coordinates locked. You can enter flat/house details in the address box.");
                }
            })
            .catch(() => {
                this.setStatusMessage("📍 Coordinates locked. Enter your address in the box above.");
            });
    }

    // 10. Direct Search Execution
    searchLocation(query) {
        if (!query || !query.trim()) return;
        const cleanQuery = query.trim();
        this.setStatusMessage(`Searching for "${cleanQuery}" across Gujarat...`);

        fetch(`/api/location/search?q=${encodeURIComponent(cleanQuery)}&request_id=direct`)
            .then(r => r.json())
            .then(data => {
                const results = data.results || [];
                if (results.length > 0) {
                    this.selectSuggestion(results[0]);
                } else {
                    this.setStatusMessage(`No match found for "${cleanQuery}". You can click on the map to place your pin.`, true);
                }
            })
            .catch(() => {
                this.setStatusMessage("Location search is temporarily unavailable. You can select the location manually on the map.", true);
            });
    }

    // 11. Quick Gujarat City Jump
    jumpToCity(cityName, lat, lng, zoom = 14) {
        this.setMarkerLocation(lat, lng, false, true);
        this.setAddressText(`${cityName}, Gujarat, India`, false);
        this.setStatusMessage(`Centered on ${cityName}. Type street name or drag pin to exact location.`);
    }

    // 12. Setup Confirm / Refine Location Buttons
    setupConfirmControls() {
        const confirmBtn = document.getElementById(this.confirmLocationBtnId);
        const refineBtn = document.getElementById(this.refineLocationBtnId);
        const mapWrapper = document.getElementById(this.collapsibleWrapperId);
        const confirmedCard = document.getElementById(this.confirmedCardId);

        if (confirmBtn) {
            confirmBtn.addEventListener('click', () => {
                const latInput = document.getElementById(this.latInputId);
                const lngInput = document.getElementById(this.lngInputId);
                if (!latInput || !latInput.value || !lngInput || !lngInput.value) {
                    this.setStatusMessage("Please select a location on the map first.", true);
                    return;
                }

                if (mapWrapper) {
                    mapWrapper.classList.add('d-none');
                }
                if (confirmedCard) {
                    confirmedCard.classList.remove('d-none');
                }
                const toggleLabel = document.getElementById('map-toggle-label');
                if (toggleLabel) toggleLabel.innerText = 'Expand Map';
                this.syncConfirmationUI();
            });
        }

        if (refineBtn) {
            refineBtn.addEventListener('click', () => {
                if (mapWrapper) {
                    mapWrapper.classList.remove('d-none');
                    if (this.map) {
                        setTimeout(() => this.map.invalidateSize(), 150);
                    }
                }
                const toggleLabel = document.getElementById('map-toggle-label');
                if (toggleLabel) toggleLabel.innerText = 'Hide Map';
            });
        }
    }
}
