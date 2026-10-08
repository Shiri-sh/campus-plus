document.addEventListener("DOMContentLoaded", () => {
  const adminTab = document.querySelector("[data-admin-tab]");
  if (adminTab?.dataset.adminTab) {
    const target = adminTab.dataset.adminTab;
    document.querySelectorAll('[data-tab-group="admin"]').forEach((item) => {
      item.classList.toggle("is-active", item.dataset.tabTarget === target);
    });
    document.querySelectorAll('[data-tab-panel-group="admin"]').forEach((panel) => {
      panel.classList.toggle("hidden", panel.dataset.tabPanel !== target);
    });
  }

  document.querySelectorAll("[data-tab-target]").forEach((button) => {
    button.addEventListener("click", () => {
      const group = button.dataset.tabGroup;
      const target = button.dataset.tabTarget;

      document
        .querySelectorAll(`[data-tab-group="${group}"]`)
        .forEach((item) => item.classList.toggle("is-active", item === button));

      document.querySelectorAll(`[data-tab-panel-group="${group}"]`).forEach((panel) => {
        panel.classList.toggle("hidden", panel.dataset.tabPanel !== target);
      });
    });
  });

  const itemModal = document.getElementById("item-modal");
  const reportModal = document.getElementById("report-modal");
  const reportForm = document.querySelector("[data-report-form]");
  let activeMaterialId = "";

  const fillItemModal = (data) => {
    document.querySelector("[data-modal-name]").textContent = data.file_name;
    document.querySelector("[data-modal-course]").textContent = data.course;
    document.querySelector("[data-modal-lecturer]").textContent = data.lecturer;
    document.querySelector("[data-modal-year]").textContent = data.academic_year;
    document.querySelector("[data-modal-type]").textContent = data.material_type;
    document.querySelector("[data-modal-summary]").textContent = data.ai_summary;

    const preview = document.querySelector("[data-preview-frame]");
    preview.replaceChildren();
    if (data.preview_kind === "video") {
      const player = document.createElement("video");
      player.controls = true;
      player.src = data.preview_url;
      preview.append(player);
    } else if (data.preview_kind === "file") {
      const frame = document.createElement("iframe");
      frame.src = data.preview_url;
      frame.title = data.file_name;
      preview.append(frame);
    } else {
      preview.textContent = "No file is stored for this record yet.";
    }

    const download = document.querySelector("[data-modal-download]");
    if (download) {
      if (data.download_url) {
        download.href = data.download_url;
        download.classList.remove("hidden");
      } else {
        download.classList.add("hidden");
      }
    }
  };

  document.querySelectorAll("[data-admin-preview]").forEach((button) => {
    button.addEventListener("click", async () => {
      const response = await fetch(`/admin/materials/${button.dataset.adminPreview}`);
      if (!response.ok) {
        return;
      }
      const data = await response.json();
      const modal = document.getElementById("admin-preview-modal");
      const name = modal.querySelector("[data-modal-name]");
      const preview = modal.querySelector("[data-preview-frame]");
      const download = modal.querySelector("[data-modal-download]");
      if (name) name.textContent = data.file_name;
      preview.replaceChildren();
      if (data.preview_kind === "file") {
        const frame = document.createElement("iframe");
        frame.src = data.preview_url;
        frame.title = data.file_name;
        preview.append(frame);
      } else if (data.preview_kind === "video") {
        const player = document.createElement("video");
        player.controls = true;
        player.src = data.preview_url;
        preview.append(player);
      } else {
        preview.textContent = "No file is stored for this record yet.";
      }
      if (data.download_url) {
        download.href = data.download_url;
        download.classList.remove("hidden");
      } else {
        download.classList.add("hidden");
      }
      modal.classList.add("is-open");
    });
  });

  const openReport = (materialId) => {
    activeMaterialId = materialId;
    if (reportForm) {
      reportForm.action = `/student/materials/${materialId}/report`;
    }
    reportModal?.classList.add("is-open");
  };

  document.querySelectorAll("[data-view-material]").forEach((button) => {
    button.addEventListener("click", async () => {
      activeMaterialId = button.dataset.viewMaterial;
      const response = await fetch(`/student/materials/${activeMaterialId}`);
      if (!response.ok) {
        return;
      }
      fillItemModal(await response.json());
      itemModal?.classList.add("is-open");
    });
  });

  document.querySelectorAll("[data-report-material]").forEach((button) => {
    button.addEventListener("click", () => openReport(button.dataset.reportMaterial));
  });

  document.querySelector("[data-report-from-details]")?.addEventListener("click", () => {
    itemModal?.classList.remove("is-open");
    if (activeMaterialId) {
      openReport(activeMaterialId);
    }
  });

  document.querySelectorAll("[data-close-modal]").forEach((button) => {
    button.addEventListener("click", () => {
      button.closest(".modal")?.classList.remove("is-open");
    });
  });

  document.querySelectorAll(".modal").forEach((modal) => {
    modal.addEventListener("click", (event) => {
      if (event.target === modal) {
        modal.classList.remove("is-open");
      }
    });
  });

  const searchInput = document.querySelector("[data-typeahead]");
  const typeahead = document.querySelector("[data-suggest-list]");
  if (searchInput && typeahead) {
    const renderSuggestions = (items) => {
      typeahead.replaceChildren();
      items.forEach((item) => {
        const button = document.createElement("button");
        button.type = "button";
        button.dataset.suggest = item.label;
        const hint = document.createElement("small");
        hint.textContent = item.hint;
        button.append(item.label, hint);
        typeahead.append(button);
      });
      typeahead.classList.toggle("is-open", items.length > 0);
    };

    searchInput.addEventListener("input", async () => {
      const query = searchInput.value.trim();
      if (!query) {
        renderSuggestions([]);
        return;
      }
      const response = await fetch(`/student/suggest?q=${encodeURIComponent(query)}`);
      if (!response.ok) {
        return;
      }
      renderSuggestions(await response.json());
    });

    typeahead.addEventListener("mousedown", (event) => {
      const suggestion = event.target.closest("[data-suggest]");
      if (!suggestion) {
        return;
      }
      searchInput.value = suggestion.dataset.suggest;
      searchInput.form?.submit();
    });

    searchInput.addEventListener("blur", () => {
      window.setTimeout(() => typeahead.classList.remove("is-open"), 150);
    });
  }

  const dropzone = document.querySelector("[data-dropzone]");
  const fileInput = document.querySelector("[data-upload-file]");
  const videoLink = document.querySelector("[data-video-link]");
  const previewBox = document.querySelector("[data-ai-preview]");
  const statusText = document.querySelector("[data-classify-status]");
  const spinner = document.querySelector("[data-classify-spinner]");
  const confidence = document.querySelector("[data-confidence]");
  const confidenceInput = document.querySelector("[data-confidence-input]");
  const fileNameLabel = document.querySelector("[data-upload-name]");

  const showPrediction = (data) => {
    document.getElementById("predicted-course").value = String(data.course_id);
    document.getElementById("predicted-year").value = String(data.academic_year);
    document.getElementById("predicted-type").value = data.material_type;
    confidenceInput.value = `${data.confidence}%`;
    confidence.textContent = `Confidence ${data.confidence}%`;
    confidence.classList.remove("hidden");
    spinner.classList.add("hidden");
    statusText.textContent = "Confirm the suggested classification or edit it manually.";
  };

  const classifyUpload = async (body) => {
    previewBox.classList.remove("hidden");
    spinner.classList.remove("hidden");
    confidence.classList.add("hidden");
    statusText.textContent = "Classifying the selected material...";
    const response = await fetch("/upload/classify", { method: "POST", body });
    const data = await response.json();
    if (!response.ok) {
      spinner.classList.add("hidden");
      statusText.textContent = data.error || "Classification failed.";
      return;
    }
    showPrediction(data);
  };

  fileInput?.addEventListener("change", () => {
    if (!fileInput.files[0]) {
      return;
    }
    fileNameLabel.textContent = fileInput.files[0].name;
    const body = new FormData();
    body.append("file", fileInput.files[0]);
    classifyUpload(body);
  });

  dropzone?.addEventListener("dragover", (event) => {
    event.preventDefault();
    dropzone.classList.add("is-active");
  });

  dropzone?.addEventListener("dragleave", () => dropzone.classList.remove("is-active"));

  dropzone?.addEventListener("drop", (event) => {
    event.preventDefault();
    dropzone.classList.remove("is-active");
    const file = event.dataTransfer.files[0];
    if (!file) {
      return;
    }
    fileNameLabel.textContent = file.name;
    const body = new FormData();
    body.append("file", file);
    classifyUpload(body);
  });

  document.querySelector("[data-classify-link]")?.addEventListener("click", () => {
    if (!videoLink.value.trim()) {
      return;
    }
    fileNameLabel.textContent = videoLink.value.trim();
    const body = new FormData();
    body.append("video_link", videoLink.value.trim());
    classifyUpload(body);
  });
});
