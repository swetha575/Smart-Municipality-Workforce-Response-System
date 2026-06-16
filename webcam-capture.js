(function () {
    const webcamModules = document.querySelectorAll(".webcam-capture");

    webcamModules.forEach((module) => {
        const hiddenInput = document.getElementById(module.dataset.hiddenInputId);
        const fileInput = document.getElementById(module.dataset.fileInputId);
        const video = module.querySelector(".webcam-video");
        const canvas = module.querySelector(".webcam-canvas");
        const preview = module.querySelector(".webcam-preview");
        const placeholder = module.querySelector(".camera-placeholder");
        const status = module.querySelector(".camera-status");
        const startButton = module.querySelector(".webcam-start");
        const captureButton = module.querySelector(".webcam-capture-btn");
        const retakeButton = module.querySelector(".webcam-retake");
        let stream = null;

        const setStatus = (message) => {
            if (status) {
                status.textContent = message;
            }
        };

        const showPreview = () => {
            preview.classList.remove("d-none");
            video.classList.add("d-none");
            canvas.classList.add("d-none");
            placeholder.classList.add("d-none");
            captureButton.classList.add("d-none");
            retakeButton.classList.remove("d-none");
            startButton.classList.add("d-none");
        };

        const showLive = () => {
            video.classList.remove("d-none");
            preview.classList.add("d-none");
            placeholder.classList.add("d-none");
            captureButton.classList.remove("d-none");
            retakeButton.classList.add("d-none");
            startButton.classList.add("d-none");
        };

        const resetCapture = () => {
            if (hiddenInput) {
                hiddenInput.value = "";
            }
            preview.src = "";
            preview.classList.add("d-none");
            placeholder.classList.remove("d-none");
            captureButton.classList.add("d-none");
            retakeButton.classList.add("d-none");
            startButton.classList.remove("d-none");
            if (fileInput) {
                fileInput.value = "";
            }
        };

        const stopStream = () => {
            if (stream) {
                stream.getTracks().forEach((track) => track.stop());
                stream = null;
            }
        };

        startButton?.addEventListener("click", async () => {
            if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
                setStatus("Webcam access is not supported in this browser. Use image upload instead.");
                return;
            }
            try {
                stopStream();
                stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "user" }, audio: false });
                video.srcObject = stream;
                showLive();
                setStatus("Camera is live. Capture a clear frontal face image.");
            } catch (error) {
                setStatus("Unable to access the webcam. Check browser permissions or use image upload.");
            }
        });

        captureButton?.addEventListener("click", () => {
            if (!stream) {
                setStatus("Start the camera before capturing.");
                return;
            }
            const width = video.videoWidth || 640;
            const height = video.videoHeight || 480;
            canvas.width = width;
            canvas.height = height;
            const context = canvas.getContext("2d");
            context.drawImage(video, 0, 0, width, height);
            const dataUrl = canvas.toDataURL("image/jpeg", 0.92);
            if (hiddenInput) {
                hiddenInput.value = dataUrl;
            }
            if (fileInput) {
                fileInput.value = "";
            }
            preview.src = dataUrl;
            showPreview();
            setStatus("Live face image captured successfully.");
            stopStream();
        });

        retakeButton?.addEventListener("click", () => {
            resetCapture();
            setStatus("Ready to start the camera again.");
        });

        fileInput?.addEventListener("change", () => {
            if (fileInput.files && fileInput.files.length > 0) {
                if (hiddenInput) {
                    hiddenInput.value = "";
                }
                stopStream();
                preview.src = "";
                preview.classList.add("d-none");
                video.classList.add("d-none");
                placeholder.classList.remove("d-none");
                captureButton.classList.add("d-none");
                retakeButton.classList.add("d-none");
                startButton.classList.remove("d-none");
                setStatus("Fallback image selected from device storage.");
            }
        });

        module.closest("form")?.addEventListener("submit", () => {
            stopStream();
        });

        window.addEventListener("beforeunload", stopStream);
    });

    document.querySelectorAll(".geo-fill").forEach((button) => {
        button.addEventListener("click", () => {
            const target = document.getElementById(button.dataset.targetId);
            if (!target) {
                return;
            }
            if (!navigator.geolocation) {
                target.value = "Geolocation not supported in this browser";
                return;
            }
            button.disabled = true;
            button.textContent = "Locating...";
            navigator.geolocation.getCurrentPosition(
                (position) => {
                    target.value = `${position.coords.latitude.toFixed(6)}, ${position.coords.longitude.toFixed(6)}`;
                    button.disabled = false;
                    button.textContent = "Use Current Location";
                },
                () => {
                    target.value = "Unable to fetch current location";
                    button.disabled = false;
                    button.textContent = "Use Current Location";
                },
                { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 }
            );
        });
    });
})();
