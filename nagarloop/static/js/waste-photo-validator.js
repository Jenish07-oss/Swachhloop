/**
 * NAGARLOOP — Browser-Side AI Waste Photo Validator (Strict Hard Block Edition)
 * 
 * Enforces client-side AI image relevance verification using MobileNet.
 * Rules:
 *  - Booking Submit buttons are HARD DISABLED by default.
 *  - Only an explicit AI PASS (waste relevant & confidence >= threshold) unlocks booking.
 *  - Changing, replacing, or retaking a photo IMMEDIATELY resets validation and locks booking.
 *  - Non-waste, low-confidence, uncertain photos, or AI errors HARD BLOCK booking.
 */

const AI_CONFIG = {
  HIGH_CONFIDENCE: 0.30,   // Strict score threshold required for PASS
  MEDIUM_CONFIDENCE: 0.12,
  RELEVANT_KEYWORDS: [
    'bottle', 'can', 'bag', 'box', 'carton', 'container', 'bucket', 'tub',
    'ashcan', 'garbage', 'rubbish', 'trash', 'waste', 'crate', 'barrel', 'tin',
    'jar', 'wrapper', 'packet', 'cardboard', 'paper', 'plastic', 'envelope',
    'tire', 'shoe', 'boot', 'electronic', 'telephone', 'cellular', 'appliance',
    'refrigerator', 'microwave', 'computer', 'monitor', 'keyboard', 'television',
    'screen', 'washer', 'heater', 'cable', 'wire', 'scrap', 'litter', 'debris',
    'compost', 'fruit', 'vegetable', 'food', 'banana', 'apple', 'orange', 'peel',
    'cabbage', 'leaf', 'pot', 'pottery', 'porcelain', 'glass', 'cup', 'mug',
    'plate', 'bowl', 'tray', 'foil', 'basket', 'dustbin', 'recycling', 'dumpster'
  ]
};

class WastePhotoValidator {
  constructor() {
    this.model = null;
    this.isModelLoading = false;
    this.modelLoadFailed = false;
    this.videoStream = null;
    this.activeImageSrc = null;
    this.activePhotoHash = null; // Uniquely binds validation to current photo
    this.photoValidated = false;
    this.bookingAllowed = false;
    this.submitButtonIds = [
      'btn-submit-pickup',
      'btn-submit-pickup-mobile',
      'btn-submit-public',
      'btn-submit-public-mobile',
      'btn-submit-society'
    ];
  }

  // Register submit button IDs to lock/unlock
  registerSubmitButtons(ids) {
    if (Array.isArray(ids)) {
      this.submitButtonIds = [...new Set([...this.submitButtonIds, ...ids])];
    }
    this.lockBooking();
  }

  // Hard lock all booking submit buttons
  lockBooking() {
    this.photoValidated = false;
    this.bookingAllowed = false;

    this.submitButtonIds.forEach(id => {
      const btn = document.getElementById(id);
      if (btn) {
        btn.disabled = true;
        btn.classList.add('disabled', 'opacity-50');
        btn.setAttribute('aria-disabled', 'true');
        btn.title = "A valid waste photo must be verified before booking.";
      }
    });
  }

  // Unlock all booking submit buttons on explicit PASS
  unlockBooking() {
    this.photoValidated = true;
    this.bookingAllowed = true;

    this.submitButtonIds.forEach(id => {
      const btn = document.getElementById(id);
      if (btn) {
        btn.disabled = false;
        btn.classList.remove('disabled', 'opacity-50');
        btn.removeAttribute('aria-disabled');
        btn.title = "Confirm & Create Waste Pickup";
      }
    });
  }

  // Check if form submission is allowed
  canSubmit() {
    return this.photoValidated && this.bookingAllowed;
  }

  // Pre-load MobileNet model lazily
  async loadModel() {
    if (this.model) return this.model;
    if (this.modelLoadFailed) return null;
    if (this.isModelLoading) return null;

    this.isModelLoading = true;
    try {
      if (typeof mobilenet !== 'undefined') {
        this.model = await mobilenet.load({ version: 2, alpha: 0.50 });
        console.log("NagarLoop AI: MobileNet model loaded successfully.");
      } else {
        console.warn("NagarLoop AI: mobilenet library not loaded.");
        this.modelLoadFailed = true;
      }
    } catch (err) {
      console.warn("NagarLoop AI: Could not load MobileNet model.", err);
      this.modelLoadFailed = true;
    } finally {
      this.isModelLoading = false;
    }
    return this.model;
  }

  // Open Browser Live Camera
  async openCamera(videoElemId, modalElemId, errorElemId) {
    const videoElem = document.getElementById(videoElemId || 'camera-video');
    const modalElem = document.getElementById(modalElemId || 'camera-modal');
    const errorElem = document.getElementById(errorElemId || 'camera-error-msg');

    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      this.showCameraError(errorElem, "Camera access is not supported on this browser/device. Please upload a photo from your gallery.");
      return;
    }

    try {
      this.videoStream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: { ideal: "environment" }, width: { ideal: 1280 }, height: { ideal: 720 } }
      });
      videoElem.srcObject = this.videoStream;
      videoElem.play();

      if (modalElem) modalElem.classList.remove('d-none');
      if (errorElem) errorElem.classList.add('d-none');
    } catch (err) {
      console.warn("NagarLoop Camera Error:", err);
      this.showCameraError(errorElem, "Camera permission denied or unavailable. Please upload a photo from your gallery.");
    }
  }

  showCameraError(errorElem, msg) {
    if (errorElem) {
      errorElem.textContent = msg;
      errorElem.classList.remove('d-none');
    } else {
      alert(msg);
    }
  }

  // Snap photo from live camera canvas
  snapPhoto(videoElemId, modalElemId, fileInputId, previewImgId) {
    const videoElem = document.getElementById(videoElemId || 'camera-video');
    const modalElem = document.getElementById(modalElemId || 'camera-modal');
    const fileInput = document.getElementById(fileInputId || 'photo-file-input');
    const previewImg = document.getElementById(previewImgId || 'photo-preview-img');

    if (!videoElem || !videoElem.videoWidth) return;

    // Reset previous validation state immediately upon new photo capture
    this.resetPhotoState();

    const canvas = document.createElement('canvas');
    canvas.width = videoElem.videoWidth;
    canvas.height = videoElem.videoHeight;
    const ctx = canvas.getContext('2d');
    ctx.drawImage(videoElem, 0, 0, canvas.width, canvas.height);

    const dataUrl = canvas.toDataURL('image/jpeg', 0.85);
    this.activeImageSrc = dataUrl;
    this.activePhotoHash = 'snap_' + Date.now() + '_' + Math.random().toString(36).substring(2, 9);

    // Convert DataURL to File object for form submission
    canvas.toBlob((blob) => {
      const file = new File([blob], `waste_photo_${Date.now()}.jpg`, { type: 'image/jpeg' });
      const container = new DataTransfer();
      container.items.add(file);
      if (fileInput) fileInput.files = container.files;

      if (previewImg) {
        previewImg.src = dataUrl;
      }
      this.closeCamera(modalElemId);
      this.validateActivePhoto();
    }, 'image/jpeg', 0.85);
  }

  // Close live camera
  closeCamera(modalElemId) {
    const modalElem = document.getElementById(modalElemId || 'camera-modal');
    if (this.videoStream) {
      this.videoStream.getTracks().forEach(track => track.stop());
      this.videoStream = null;
    }
    if (modalElem) modalElem.classList.add('d-none');
  }

  // Handle Gallery Input File
  handleFileInput(inputElem, previewImgId) {
    if (!inputElem || !inputElem.files || !inputElem.files[0]) {
      this.resetPhoto();
      return;
    }

    // Reset previous validation state immediately upon file selection change
    this.resetPhotoState();

    const file = inputElem.files[0];
    this.activePhotoHash = 'file_' + file.name + '_' + file.size + '_' + Date.now();
    const reader = new FileReader();

    reader.onload = (e) => {
      this.activeImageSrc = e.target.result;
      const previewImg = document.getElementById(previewImgId || 'photo-preview-img');
      if (previewImg) previewImg.src = this.activeImageSrc;
      this.validateActivePhoto();
    };
    reader.readAsDataURL(file);
  }

  // Reset photo state and lock booking immediately
  resetPhotoState() {
    this.lockBooking();
    const hiddenCheck = document.getElementById('ai-image-check');
    const hiddenConf = document.getElementById('ai-confidence');
    if (hiddenCheck) hiddenCheck.value = 'pending';
    if (hiddenConf) hiddenConf.value = '0.0';
  }

  // Validate active photo using TensorFlow.js MobileNet
  async validateActivePhoto() {
    const photoHashAtStart = this.activePhotoHash;
    this.lockBooking(); // Ensure booking is hard locked while checking

    const previewContainer = document.getElementById('photo-preview-container');
    const spinner = document.getElementById('ai-loading-spinner');
    const resultCard = document.getElementById('ai-result-card');
    const badge = document.getElementById('ai-badge');
    const labelElem = document.getElementById('ai-prediction-label');
    const feedbackElem = document.getElementById('ai-feedback-msg');
    const continueMsg = document.getElementById('ai-continue-msg');
    const hiddenCheck = document.getElementById('ai-image-check');
    const hiddenConf = document.getElementById('ai-confidence');

    if (previewContainer) previewContainer.classList.remove('d-none');
    if (spinner) spinner.classList.remove('d-none');
    if (resultCard) resultCard.classList.add('d-none');
    if (continueMsg) continueMsg.classList.add('d-none');

    // Create offscreen image element
    const img = new Image();
    img.crossOrigin = 'anonymous';
    img.src = this.activeImageSrc;

    await new Promise(resolve => { img.onload = resolve; img.onerror = resolve; });

    // Check if photo was replaced during async image loading
    if (this.activePhotoHash !== photoHashAtStart) return;

    let model = await this.loadModel();

    // Check again if photo changed during model loading
    if (this.activePhotoHash !== photoHashAtStart) return;

    if (spinner) spinner.classList.add('d-none');
    if (resultCard) resultCard.classList.remove('d-none');

    // Hard block if AI model fails to load
    if (!model) {
      if (badge) {
        badge.className = 'badge bg-danger text-white fw-bold';
        badge.textContent = '⚠️ Verification Unavailable';
      }
      if (labelElem) labelElem.textContent = 'Model Loading Error';
      if (feedbackElem) feedbackElem.textContent = '⚠️ Photo verification is currently unavailable. Please check your connection and try again.';
      if (hiddenCheck) hiddenCheck.value = 'failed';
      if (hiddenConf) hiddenConf.value = '0.0';
      this.lockBooking();
      return;
    }

    try {
      // Run MobileNet classification
      const predictions = await model.classify(img, 5);
      console.log("NagarLoop AI Predictions:", predictions);

      // Check if photo changed during inference
      if (this.activePhotoHash !== photoHashAtStart) return;

      let highestWasteScore = 0;
      let topMatchedLabel = '';

      if (predictions && predictions.length > 0) {
        for (let p of predictions) {
          const classNameLower = p.className.toLowerCase();
          const isWasteMatch = AI_CONFIG.RELEVANT_KEYWORDS.some(kw => classNameLower.includes(kw));

          if (isWasteMatch) {
            if (p.probability > highestWasteScore) {
              highestWasteScore = p.probability;
              topMatchedLabel = p.className.split(',')[0];
            }
          }
        }
      }

      const topClass = predictions[0] ? predictions[0].className.split(',')[0] : 'Object';
      const confidencePct = Math.round((highestWasteScore || predictions[0].probability) * 100);

      if (highestWasteScore >= AI_CONFIG.HIGH_CONFIDENCE) {
        // State 1: HIGH CONFIDENCE PASS -> UNLOCK BOOKING
        if (badge) {
          badge.className = 'badge bg-success text-white fw-bold';
          badge.textContent = '✓ Waste Photo Verified';
        }
        if (labelElem) labelElem.textContent = `Detected: ${topMatchedLabel || topClass} (${confidencePct}% relevance)`;
        if (feedbackElem) feedbackElem.textContent = '✓ Waste photo verified. You can continue with booking.';
        if (continueMsg) continueMsg.classList.remove('d-none');
        if (hiddenCheck) hiddenCheck.value = 'passed';
        if (hiddenConf) hiddenConf.value = highestWasteScore.toFixed(2);
        this.unlockBooking(); // UNLOCK BOOKING BUTTON
      } else {
        // State 2 & 3: UNCERTAIN OR NON-WASTE -> HARD BLOCK BOOKING
        if (badge) {
          badge.className = 'badge bg-danger text-white fw-bold';
          badge.textContent = '✕ Photo Rejected (Not Waste)';
        }
        if (labelElem) labelElem.textContent = `Detected: ${topClass}`;
        if (feedbackElem) feedbackElem.textContent = '⚠️ This photo does not appear to show waste. Please take or upload a clear photo of the waste before booking.';
        if (hiddenCheck) hiddenCheck.value = 'failed';
        if (hiddenConf) hiddenConf.value = highestWasteScore.toFixed(2);
        this.lockBooking(); // HARD BLOCK BOOKING BUTTON
      }
    } catch (err) {
      console.warn("NagarLoop AI Inference Error:", err);
      if (badge) {
        badge.className = 'badge bg-danger text-white fw-bold';
        badge.textContent = '⚠️ Verification Failed';
      }
      if (labelElem) labelElem.textContent = 'Inference Error';
      if (feedbackElem) feedbackElem.textContent = '⚠️ Image check could not verify this photo. Please retake a clear photo of waste.';
      if (hiddenCheck) hiddenCheck.value = 'failed';
      if (hiddenConf) hiddenConf.value = '0.0';
      this.lockBooking(); // HARD BLOCK BOOKING BUTTON
    }
  }

  // Reset photo selection completely
  resetPhoto(fileInputId, previewContainerId) {
    const fileInput = document.getElementById(fileInputId || 'photo-file-input');
    const previewContainer = document.getElementById(previewContainerId || 'photo-preview-container');

    if (fileInput) fileInput.value = '';
    this.activeImageSrc = null;
    this.activePhotoHash = null;

    if (previewContainer) previewContainer.classList.add('d-none');
    this.resetPhotoState();
  }
}

// Global Singleton Instance
window.wasteValidator = new WastePhotoValidator();

// Preload model on DOM ready and lock submit buttons
document.addEventListener('DOMContentLoaded', () => {
  window.wasteValidator.lockBooking();

  // Attach form submit guard to prevent JS bypass attempts
  document.querySelectorAll('form').forEach(form => {
    if (form.querySelector('input[name="photo"]')) {
      form.addEventListener('submit', function (e) {
        const checkVal = document.getElementById('ai-image-check') ? document.getElementById('ai-image-check').value : '';
        const confVal = document.getElementById('ai-confidence') ? parseFloat(document.getElementById('ai-confidence').value) : 0;
        
        if (!window.wasteValidator.canSubmit() || checkVal !== 'passed' || confVal < 0.30) {
          e.preventDefault();
          e.stopPropagation();
          alert("⚠️ Booking blocked: A valid waste photo must be verified before booking. Please upload or take a clear photo of waste.");
          return false;
        }
      });
    }
  });

  if (typeof mobilenet !== 'undefined') {
    setTimeout(() => {
      window.wasteValidator.loadModel();
    }, 1000);
  }
});
