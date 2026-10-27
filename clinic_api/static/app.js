/* Interactive examples use the same API and database as the documented endpoints. */
(() => {
  "use strict";

  const byId = (id) => document.getElementById(id);
  const pretty = (value) => JSON.stringify(value, null, 2);
  const initialOutputs = new Map();
  const state = {
    clinicId: null,
    slotId: null,
    bookingId: null,
    bookingActive: false,
    slotCancelled: false,
    busy: false,
  };
  const httpNames = {
    200: "OK",
    201: "Created",
    204: "No Content",
    404: "Not Found",
    409: "Conflict",
    422: "Validation Error",
    500: "Server Error",
    503: "Service Unavailable",
  };

  class ExampleError extends Error {
    constructor(code, message) {
      super(message);
      this.name = "ExampleError";
      this.code = code;
    }
  }

  function setStatus(element, label, tone = "idle") {
    if (!element) return;
    element.textContent = label;
    element.dataset.state = tone;
    element.setAttribute("role", "status");
    element.setAttribute("aria-live", "polite");
  }

  function setApiStatus(available, message) {
    const indicator = byId("api-status");
    setStatus(
      indicator,
      available ? "API connected" : "API unavailable",
      available ? "success" : "error",
    );
    if (indicator)
      indicator.title =
        message || "Connected to this server's live booking API.";
  }

  function outputFor(action) {
    return byId(action === "race" ? "race-output" : `${action}-response`);
  }

  function render(action, body, label, tone, elapsed = null) {
    const output = outputFor(action);
    if (output) {
      output.textContent = typeof body === "string" ? body : pretty(body);
      output.dataset.state = tone;
      output.setAttribute("aria-busy", tone === "loading" ? "true" : "false");
    }
    setStatus(byId(`${action}-result`), label, tone);
    const timing = byId(`${action}-time`);
    if (timing)
      timing.textContent = elapsed === null ? "" : `${Math.round(elapsed)} ms`;
  }

  function renderResponse(action, result) {
    const label =
      `${result.status} ${httpNames[result.status] || result.statusText}`.trim();
    const tone = result.ok
      ? "success"
      : result.status === 409
        ? "warning"
        : "error";
    render(
      action,
      result.status === 204
        ? "No response body. Cancellation completed (204 No Content)."
        : result.data,
      label,
      tone,
      result.elapsed,
    );
  }

  function renderError(action, error) {
    const code = error.code || "REQUEST_FAILED";
    const message =
      error instanceof ExampleError
        ? error.message
        : "The request could not be completed. Check the API connection and try again.";
    render(
      action,
      { error: { code, message } },
      code === "INVALID_JSON" || code === "STEP_REQUIRED"
        ? "Request not sent"
        : "Request failed",
      "error",
    );
  }

  async function request(path, { method = "GET", body } = {}) {
    const started = performance.now();
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 20000);
    try {
      const response = await fetch(path, {
        method,
        headers:
          body === undefined
            ? { Accept: "application/json" }
            : {
                Accept: "application/json",
                "Content-Type": "application/json",
              },
        body: body === undefined ? undefined : JSON.stringify(body),
        cache: "no-store",
        signal: controller.signal,
      });
      const raw = await response.text();
      let data = null;
      if (raw) {
        try {
          data = JSON.parse(raw);
        } catch {
          data = raw;
        }
      }
      setApiStatus(
        response.status < 500,
        response.status >= 500
          ? "The server returned an error. See the response for details."
          : undefined,
      );
      return {
        ok: response.ok,
        status: response.status,
        statusText: response.statusText,
        data,
        elapsed: performance.now() - started,
      };
    } catch (error) {
      setApiStatus(
        false,
        "Unable to reach the API. Check that the server is running.",
      );
      if (error.name === "AbortError") {
        throw new ExampleError(
          "REQUEST_TIMEOUT",
          "The API did not respond within 20 seconds. A write may still have completed; browse records before retrying.",
        );
      }
      throw new ExampleError(
        "NETWORK_ERROR",
        "Could not reach the API. Check that the server is running and your connection is available. Browse records before retrying a write.",
      );
    } finally {
      window.clearTimeout(timeout);
    }
  }

  async function exclusive(action, operation) {
    if (state.busy) return;
    state.busy = true;
    const controls = [...document.querySelectorAll("button, select")].map(
      (element) => ({
        element,
        disabled: element.disabled,
      }),
    );
    const drafts = [...document.querySelectorAll("textarea")].map(
      (element) => ({
        element,
        readOnly: element.readOnly,
      }),
    );
    for (const { element } of controls) {
      element.disabled = true;
      element.setAttribute("aria-busy", "true");
    }
    for (const { element } of drafts) element.readOnly = true;
    render(action, "Waiting for the API response…", "Sending…", "loading");
    try {
      await operation();
    } catch (error) {
      renderError(action, error);
    } finally {
      for (const { element, disabled } of controls) {
        element.disabled = disabled;
        element.setAttribute("aria-busy", "false");
      }
      for (const { element, readOnly } of drafts) element.readOnly = readOnly;
      state.busy = false;
    }
  }

  function readDraft(action) {
    const field = byId(`${action}-request`);
    let body;
    try {
      body = JSON.parse(field?.value || "");
    } catch {
      throw new ExampleError(
        "INVALID_JSON",
        "Enter valid JSON with double-quoted keys and values. Check for missing commas or trailing commas, then try again.",
      );
    }
    if (body === null || Array.isArray(body) || typeof body !== "object") {
      throw new ExampleError(
        "INVALID_JSON",
        'The request must be a JSON object, for example {"name": "Sunrise Clinic"}.',
      );
    }
    return body;
  }

  function requireContext(key, message) {
    if (!state[key]) throw new ExampleError("STEP_REQUIRED", message);
    return encodeURIComponent(state[key]);
  }

  function patchDraft(action, changes) {
    const field = byId(`${action}-request`);
    if (!field) return true;
    try {
      const body = JSON.parse(field.value);
      if (body === null || Array.isArray(body) || typeof body !== "object")
        return false;
      field.value = pretty({ ...body, ...changes });
      return true;
    } catch {
      // Keep an unfinished user edit intact instead of silently replacing it.
      return false;
    }
  }

  function describeContext(message) {
    const summary = byId("context-summary");
    if (summary) summary.textContent = message;
  }

  function updateContext() {
    for (const [name, value] of [
      ["clinic", state.clinicId],
      ["slot", state.slotId],
      ["booking", state.bookingId],
    ]) {
      const element = byId(`context-${name}`);
      if (!element) continue;
      const cancelled =
        (name === "booking" && !state.bookingActive) ||
        (name === "slot" && state.slotCancelled);
      const suffix = value && cancelled ? " · cancelled" : "";
      element.textContent = value
        ? `${value.slice(0, 8)}…${suffix}`
        : "Not created";
      element.title = value || `Create a ${name} to see its identifier.`;
    }
    const slotEndpoint = byId("slot-endpoint");
    if (slotEndpoint)
      slotEndpoint.textContent = `/clinics/${state.clinicId || "{clinic_id}"}/slots`;
    const bookingEndpoint = byId("cancel-booking-endpoint");
    if (bookingEndpoint)
      bookingEndpoint.textContent = `/bookings/${state.bookingId || "{booking_id}"}`;
  }

  function clearResults(actions) {
    for (const action of actions) {
      render(
        action,
        initialOutputs.get(action) ||
          "Run this request to see the live response.",
        "Not run",
        "idle",
      );
    }
  }

  function futureSlot() {
    const starts = new Date();
    starts.setUTCDate(starts.getUTCDate() + 1);
    starts.setUTCHours(10, 0, 0, 0);
    return {
      starts_at: starts.toISOString(),
      ends_at: new Date(starts.getTime() + 30 * 60 * 1000).toISOString(),
    };
  }

  function resetExamples({ initial = false } = {}) {
    if (state.busy) return;
    Object.assign(state, {
      clinicId: null,
      slotId: null,
      bookingId: null,
      bookingActive: false,
      slotCancelled: false,
    });
    const drafts = {
      clinic: {
        name: "Sunrise Clinic (demo)",
        address: "123 Health St, Bangalore",
      },
      slot: futureSlot(),
      booking: {
        slot_id: "<create a slot first>",
        patient_name: "Dharshitha",
        patient_email: "darla@example.com",
      },
      conflict: {
        slot_id: "<create a slot first>",
        patient_name: "Another patient",
        patient_email: "another@example.com",
      },
    };
    for (const [action, body] of Object.entries(drafts)) {
      const field = byId(`${action}-request`);
      if (field) field.value = pretty(body);
    }
    clearResults([
      "clinic",
      "slot",
      "booking",
      "conflict",
      "cancel-booking",
      "race",
      "browse",
    ]);
    updateContext();
    describeContext(
      initial
        ? "Start by creating a demo clinic. These examples send real requests to your API."
        : "Examples reset. Previously created clinics, slots and bookings remain in the API; no records were deleted.",
    );
  }

  async function createClinic() {
    const result = await request("/clinics", {
      method: "POST",
      body: readDraft("clinic"),
    });
    renderResponse("clinic", result);
    if (!result.ok) return;
    state.clinicId = result.data.id;
    state.slotId = null;
    state.bookingId = null;
    state.bookingActive = false;
    state.slotCancelled = false;
    patchDraft("booking", { slot_id: "<create a slot first>" });
    patchDraft("conflict", { slot_id: "<create a slot first>" });
    clearResults(["slot", "booking", "conflict", "cancel-booking"]);
    updateContext();
    describeContext("Clinic created. Next, publish a slot for this clinic.");
  }

  async function createSlot() {
    const clinicId = requireContext(
      "clinicId",
      "Create a clinic first, then publish a slot for that clinic.",
    );
    const result = await request(`/clinics/${clinicId}/slots`, {
      method: "POST",
      body: readDraft("slot"),
    });
    renderResponse("slot", result);
    if (!result.ok) return;
    state.slotId = result.data.id;
    state.slotCancelled = false;
    state.bookingId = null;
    state.bookingActive = false;
    const updatedBooking = patchDraft("booking", { slot_id: state.slotId });
    const updatedConflict = patchDraft("conflict", { slot_id: state.slotId });
    clearResults(["booking", "conflict", "cancel-booking"]);
    updateContext();
    describeContext(
      updatedBooking && updatedConflict
        ? "Slot published. Book it once, then send the duplicate request to see the conflict response."
        : "Slot published. An unfinished JSON edit was preserved; fix it and copy this slot ID into its slot_id field before booking.",
    );
  }

  async function createBooking(action) {
    requireContext(
      "slotId",
      "Publish a slot first. Its identifier will be added to the booking examples.",
    );
    const result = await request("/bookings", {
      method: "POST",
      body: readDraft(action),
    });
    renderResponse(action, result);
    if (!result.ok) {
      if (result.data?.error?.code === "SLOT_ALREADY_BOOKED") {
        describeContext(
          "The API rejected the duplicate booking. Cancel the current booking to release its slot, or publish another slot.",
        );
      }
      return;
    }
    state.bookingId = result.data.id;
    state.bookingActive = result.data.status === "confirmed";
    if (result.data.slot_id !== state.slotId) {
      state.slotId = result.data.slot_id;
      // A custom payload may refer to a different slot. Refresh its owning clinic
      // without treating a follow-up read failure as a failed booking creation.
      state.clinicId = null;
      try {
        const slot = await request(
          `/slots/${encodeURIComponent(state.slotId)}`,
        );
        if (slot.ok) state.clinicId = slot.data.clinic_id;
      } catch {
        // The successful booking and its ID remain available for cancellation.
      }
    }
    state.slotCancelled = false;
    patchDraft("booking", { slot_id: state.slotId });
    patchDraft("conflict", { slot_id: state.slotId });
    updateContext();
    describeContext(
      action === "conflict"
        ? "The slot was available, so this request created a booking. Send it again to see a 409 conflict."
        : "Booking confirmed. Try the duplicate request, or cancel this booking to release the slot.",
    );
  }

  async function cancelBooking() {
    const bookingId = requireContext(
      "bookingId",
      "Create a booking first so there is a booking to cancel.",
    );
    const result = await request(`/bookings/${bookingId}`, {
      method: "DELETE",
    });
    renderResponse("cancel-booking", result);
    if (!result.ok) return;
    state.bookingActive = false;
    updateContext();
    describeContext(
      "Booking cancelled. A future, active slot can now be booked again. Repeating this cancellation is safe.",
    );
  }

  async function browseRecords() {
    const resource = byId("browse-resource")?.value || "clinics";
    if (!["clinics", "slots", "bookings"].includes(resource)) {
      throw new ExampleError(
        "INVALID_RESOURCE",
        "Choose clinics, slots or bookings to browse.",
      );
    }
    let path = `/${resource}`;
    if (state.clinicId && resource === "slots")
      path = `/clinics/${encodeURIComponent(state.clinicId)}/slots`;
    if (state.clinicId && resource === "bookings")
      path += `?${new URLSearchParams({ clinic_id: state.clinicId })}`;
    const result = await request(path);
    renderResponse("browse", result);
  }

  async function cancelSlot() {
    const slotId = requireContext(
      "slotId",
      "Publish a slot first so there is a slot to cancel.",
    );
    const result = await request(`/slots/${slotId}`, { method: "DELETE" });
    renderResponse("browse", result);
    if (result.ok) {
      state.slotCancelled = true;
      updateContext();
      describeContext(
        "Slot cancelled. It remains in the history; publish a new slot to accept another booking.",
      );
    } else if (result.data?.error?.code === "SLOT_HAS_BOOKING") {
      describeContext(
        "This slot still has an active booking. Cancel its booking first, then cancel the slot.",
      );
    }
  }

  async function runRace() {
    const started = performance.now();
    const clinic = await request("/clinics", {
      method: "POST",
      body: {
        name: `Concurrency demo ${new Date().toISOString()}`,
        address: "Synthetic demonstration data",
      },
    });
    if (!clinic.ok) {
      render(
        "race",
        {
          phase: "Create demo clinic",
          status: clinic.status,
          response: clinic.data,
        },
        "Setup failed",
        "error",
        performance.now() - started,
      );
      return;
    }
    const slot = await request(
      `/clinics/${encodeURIComponent(clinic.data.id)}/slots`,
      {
        method: "POST",
        body: futureSlot(),
      },
    );
    if (!slot.ok) {
      render(
        "race",
        {
          phase: "Create demo slot",
          clinic_id: clinic.data.id,
          status: slot.status,
          response: slot.data,
        },
        "Setup failed",
        "error",
        performance.now() - started,
      );
      return;
    }
    render(
      "race",
      "Sending two booking requests together for a dedicated demo slot…",
      "Racing…",
      "loading",
    );
    // Both fetches start before either is awaited. Catch each failure separately
    // so controls stay disabled until both requests have actually settled.
    const responses = await Promise.all(
      [1, 2].map(async (number) => {
        try {
          const result = await request("/bookings", {
            method: "POST",
            body: {
              slot_id: slot.data.id,
              patient_name: `Race patient ${number}`,
              patient_email: `race${number}@example.com`,
            },
          });
          return {
            request: number,
            status: result.status,
            response: result.data,
          };
        } catch (error) {
          return {
            request: number,
            status: null,
            error: { code: error.code, message: error.message },
          };
        }
      }),
    );
    let confirmedCount = null;
    let verificationError = null;
    try {
      const verification = await request(
        `/bookings?${new URLSearchParams({ slot_id: slot.data.id, status: "confirmed" })}`,
      );
      if (verification.ok && Array.isArray(verification.data?.items)) {
        confirmedCount = verification.data.items.length;
      } else {
        verificationError = {
          status: verification.status,
          response: verification.data,
        };
      }
    } catch (error) {
      verificationError = { code: error.code, message: error.message };
    }
    const complete =
      responses.every((result) => result.status !== null) &&
      confirmedCount !== null;
    const passed =
      complete &&
      responses.filter((result) => result.status === 201).length === 1 &&
      responses.filter(
        (result) =>
          result.status === 409 &&
          result.response?.error?.code === "SLOT_ALREADY_BOOKED",
      ).length === 1 &&
      confirmedCount === 1;
    const details = {
      clinic_id: clinic.data.id,
      slot_id: slot.data.id,
      requests: responses,
      verification: {
        expected:
          "One 201 Created, one 409 SLOT_ALREADY_BOOKED, and one stored confirmed booking.",
        confirmed_bookings: confirmedCount,
        passed: complete ? passed : null,
        ...(verificationError ? { error: verificationError } : {}),
      },
    };
    const summary = responses.map((result) =>
      result.status === null
        ? `Request ${result.request} → No response (${result.error.code || "network error"})`
        : `Request ${result.request} → ${result.status} ${httpNames[result.status] || "HTTP response"}`,
    );
    summary.push(
      `Confirmed bookings: ${confirmedCount === null ? "unavailable" : confirmedCount}`,
    );
    render(
      "race",
      `${summary.join("\n")}\n\n${pretty(details)}`,
      complete
        ? passed
          ? "1 created · 1 conflict"
          : "Check failed"
        : "Result incomplete",
      complete ? (passed ? "success" : "error") : "warning",
      performance.now() - started,
    );
    describeContext(
      "Race finished using a separate demo clinic and slot. Your current example context is unchanged. Actual request results are shown below.",
    );
  }

  function initialize() {
    // Preserve the authored prerequisite and expected-status guidance for reset,
    // including the terminal's sample command and resource browser instructions.
    for (const action of [
      "clinic",
      "slot",
      "booking",
      "conflict",
      "cancel-booking",
      "race",
      "browse",
    ]) {
      const initialText = outputFor(action)?.textContent.trim();
      if (initialText) initialOutputs.set(action, initialText);
    }
    const actions = {
      clinic: createClinic,
      slot: createSlot,
      booking: () => createBooking("booking"),
      conflict: () => createBooking("conflict"),
      "cancel-booking": cancelBooking,
      race: runRace,
    };
    for (const button of document.querySelectorAll("[data-run]")) {
      const action = button.dataset.run;
      if (actions[action])
        button.addEventListener("click", () =>
          exclusive(action, actions[action]),
        );
    }
    byId("browse-button")?.addEventListener("click", () =>
      exclusive("browse", browseRecords),
    );
    byId("cancel-slot-button")?.addEventListener("click", () =>
      exclusive("browse", cancelSlot),
    );
    byId("reset-examples")?.addEventListener("click", () => resetExamples());
    byId("run-example")?.addEventListener("click", () => {
      byId("api-examples")?.scrollIntoView({
        behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches
          ? "auto"
          : "smooth",
        block: "start",
      });
      document
        .querySelector('[data-run="clinic"]')
        ?.focus({ preventScroll: true });
    });
    resetExamples({ initial: true });
    setStatus(byId("api-status"), "Connecting…", "loading");
    request("/health").catch(() => {
      // The connection indicator already contains the network recovery guidance.
    });
  }

  if (document.readyState === "loading")
    document.addEventListener("DOMContentLoaded", initialize, { once: true });
  else initialize();
})();
