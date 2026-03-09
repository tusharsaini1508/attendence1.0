(function () {
  const form = document.getElementById("attendance-form");
  if (!form) {
    return;
  }

  const endpoint = window.ATTENDANCE_CONFIG?.endpoint || "/attendance";
  const personName = document.getElementById("person_name");
  const cameraStream = document.getElementById("camera-stream");
  const cameraCanvas = document.getElementById("camera-canvas");
  const capturedPreview = document.getElementById("captured-preview");
  const startCameraBtn = document.getElementById("start-camera");
  const capturePhotoBtn = document.getElementById("capture-photo");
  const retakePhotoBtn = document.getElementById("retake-photo");
  const fetchLocationBtn = document.getElementById("fetch-location");
  const latitudeInput = document.getElementById("latitude");
  const longitudeInput = document.getElementById("longitude");
  const locationTextInput = document.getElementById("location_text");
  const locationStatus = document.getElementById("location-status");
  const submitFeedback = document.getElementById("submit-feedback");
  const searchInput = document.getElementById("record-search");
  const recordRows = Array.from(document.querySelectorAll("#records-table tbody .record-row"));
  const submitBtn = form.querySelector('button[type="submit"]');

  let stream = null;
  let capturedImageData = "";

  function setFeedback(message, isError) {
    submitFeedback.textContent = message;
    submitFeedback.style.color = isError ? "#dc2626" : "#047857";
  }

  function stopStream() {
    if (stream) {
      stream.getTracks().forEach((track) => track.stop());
      stream = null;
    }
  }

  function setCameraMode(mode) {
    cameraStream.classList.remove("active");
    capturedPreview.classList.remove("active");
    if (mode === "video") {
      cameraStream.classList.add("active");
    } else if (mode === "preview") {
      capturedPreview.classList.add("active");
    }
  }

  async function startCamera() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      setFeedback("Camera is not supported in this browser.", true);
      return;
    }

    try {
      stopStream();
      stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: "user", width: { ideal: 640 }, height: { ideal: 480 } },
        audio: false,
      });
      cameraStream.srcObject = stream;
      capturedImageData = "";
      setCameraMode("video");
      setFeedback("Camera is ready. Capture your photo.", false);
    } catch (error) {
      setFeedback("Camera access denied. Please allow permission and retry.", true);
    }
  }

  function capturePhoto() {
    if (!stream) {
      setFeedback("Start camera first.", true);
      return;
    }

    const width = cameraStream.videoWidth || 640;
    const height = cameraStream.videoHeight || 480;
    cameraCanvas.width = width;
    cameraCanvas.height = height;
    const ctx = cameraCanvas.getContext("2d");
    ctx.drawImage(cameraStream, 0, 0, width, height);
    capturedImageData = cameraCanvas.toDataURL("image/jpeg", 0.9);
    capturedPreview.src = capturedImageData;
    setCameraMode("preview");
    setFeedback("Photo captured successfully.", false);
    stopStream();
  }

  function clearCapture() {
    capturedImageData = "";
    capturedPreview.src = "";
    setFeedback("Capture a fresh photo.", false);
    startCamera();
  }

  async function reverseGeocode(lat, lon) {
    try {
      const response = await fetch(
        `https://nominatim.openstreetmap.org/reverse?format=jsonv2&lat=${lat}&lon=${lon}`,
        {
          headers: {
            Accept: "application/json",
          },
        }
      );
      if (!response.ok) {
        throw new Error("Reverse geocoding failed");
      }
      const data = await response.json();
      return data.display_name || "";
    } catch (error) {
      return "";
    }
  }

  function fetchLocation() {
    if (!navigator.geolocation) {
      locationStatus.textContent = "Geolocation is not supported by this browser.";
      return;
    }

    locationStatus.textContent = "Fetching your location...";

    navigator.geolocation.getCurrentPosition(
      async (position) => {
        const lat = position.coords.latitude.toFixed(6);
        const lon = position.coords.longitude.toFixed(6);
        latitudeInput.value = lat;
        longitudeInput.value = lon;

        const displayName = await reverseGeocode(lat, lon);
        if (displayName) {
          locationTextInput.value = displayName;
          locationStatus.textContent = `Location fetched: ${displayName}`;
        } else {
          locationTextInput.value = `${lat}, ${lon}`;
          locationStatus.textContent = `Coordinates fetched: ${lat}, ${lon}`;
        }
      },
      (error) => {
        if (error.code === 1) {
          locationStatus.textContent = "Location permission denied. Please allow and retry.";
        } else if (error.code === 2) {
          locationStatus.textContent = "Location unavailable right now. Retry in a moment.";
        } else {
          locationStatus.textContent = "Unable to fetch location.";
        }
      },
      {
        enableHighAccuracy: true,
        timeout: 12000,
        maximumAge: 0,
      }
    );
  }

  async function submitAttendance(event) {
    event.preventDefault();
    setFeedback("", false);

    const nameValue = personName.value.trim();
    const latitude = latitudeInput.value.trim();
    const longitude = longitudeInput.value.trim();
    const locationText = locationTextInput.value.trim();

    if (!nameValue) {
      setFeedback("Please enter person name.", true);
      return;
    }
    if (!capturedImageData) {
      setFeedback("Please capture photo before submitting.", true);
      return;
    }
    if (!latitude || !longitude) {
      setFeedback("Please auto-fetch location before submitting.", true);
      return;
    }

    const payload = {
      person_name: nameValue,
      image_data: capturedImageData,
      latitude,
      longitude,
      location_text: locationText,
    };

    try {
      if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.textContent = "Submitting...";
      }

      const response = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      let data = null;
      try {
        data = await response.json();
      } catch (e) {
        data = null;
      }

      if (!response.ok || !data.ok) {
        const serverError = data && data.error ? data.error : `Attendance submission failed (${response.status}).`;
        setFeedback(serverError, true);
        return;
      }

      setFeedback("Attendance submitted successfully.", false);
      setTimeout(() => {
        window.location.reload();
      }, 800);
    } catch (error) {
      setFeedback("Network error while submitting attendance.", true);
    } finally {
      if (submitBtn) {
        submitBtn.disabled = false;
        submitBtn.textContent = "Submit Attendance";
      }
    }
  }

  function setupSearch() {
    if (!searchInput || recordRows.length === 0) {
      return;
    }
    searchInput.addEventListener("input", () => {
      const keyword = searchInput.value.trim().toLowerCase();
      recordRows.forEach((row) => {
        const text = row.textContent.toLowerCase();
        row.style.display = text.includes(keyword) ? "" : "none";
      });
    });
  }

  startCameraBtn.addEventListener("click", startCamera);
  capturePhotoBtn.addEventListener("click", capturePhoto);
  retakePhotoBtn.addEventListener("click", clearCapture);
  fetchLocationBtn.addEventListener("click", fetchLocation);
  form.addEventListener("submit", submitAttendance);
  setupSearch();

  startCamera();
  fetchLocation();

  window.addEventListener("beforeunload", stopStream);
})();
