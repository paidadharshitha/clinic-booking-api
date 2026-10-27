/* Patient and clinic workflows share the same transaction-safe booking API. */
(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const PAGE_SIZE = 20;
  const state = {
    view: "book",
    clinics: [],
    clinicId: null,
    selectedSlot: null,
    lookupEmail: "",
    writeBusy: false,
    lastBooking: null,
  };
  const versions = {
    available: 0,
    manage: 0,
    patient: 0,
    clinic: 0,
    clinics: 0,
  };
  const pages = Object.fromEntries(
    ["available", "manage", "patient", "clinic"].map((key) => [
      key,
      { items: [], hasMore: false, loading: false },
    ]),
  );
  const slotDetails = new Map();
  const clinicDetails = new Map();
  const timeFormat = new Intl.DateTimeFormat(undefined, {
    hour: "numeric",
    minute: "2-digit",
  });
  const dateFormat = new Intl.DateTimeFormat(undefined, {
    weekday: "long",
    month: "long",
    day: "numeric",
    year: "numeric",
  });

  class ApiError extends Error {
    constructor(message, code = "REQUEST_FAILED", details = []) {
      super(message);
      this.code = code;
      this.details = details;
    }
  }

  function node(tag, className = "", text) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined) element.textContent = String(text);
    return element;
  }

  function button(text, className, action) {
    const element = node("button", className, text);
    element.type = "button";
    element.addEventListener("click", () => {
      if (!state.writeBusy) action();
    });
    return element;
  }

  function fieldError(id, message = "") {
    const element = $(id);
    if (!element) return;
    element.textContent = message;
    element.hidden = !message;
  }

  function notice(message, tone = "success") {
    const element = $("notice");
    element.textContent = message;
    element.dataset.state = tone;
    element.hidden = !message;
  }

  function errorMessage(error) {
    const messages = {
      SLOT_ALREADY_BOOKED:
        "Someone just booked this time. Please choose another available appointment.",
      SLOT_HAS_BOOKING:
        "This time has a confirmed appointment. Cancel its booking below before removing the time.",
      SLOT_CANCELLED:
        "This appointment time was cancelled. Please choose another time.",
      SLOT_STARTED:
        "This appointment time has already started. Choose a future time.",
      SLOT_IN_PAST: "Choose a start date and time in the future.",
      CLINIC_NOT_FOUND:
        "This clinic could not be found. Refresh the clinic list and try again.",
      SLOT_NOT_FOUND:
        "This appointment time could not be found. Refresh the available times.",
      BOOKING_NOT_FOUND:
        "This booking could not be found. Look up your appointments again.",
      DATABASE_BUSY:
        "The schedule is busy right now. Please try again shortly.",
      DATABASE_UNAVAILABLE:
        "The schedule is temporarily unavailable. Please try again shortly.",
    };
    if (messages[error.code]) return messages[error.code];
    if (error.code === "VALIDATION_ERROR" && error.details?.length) {
      const labels = {
        patient_name: "Patient name",
        patient_email: "Email address",
        name: "Clinic name",
        address: "Clinic address",
        starts_at: "Start time",
        ends_at: "End time",
      };
      return error.details
        .map((detail) => {
          const field = detail.field?.split(".").pop();
          return (labels[field] ? labels[field] + ": " : "") + detail.message;
        })
        .join(" ");
    }
    return error instanceof ApiError
      ? error.message
      : "Something went wrong. Please refresh and try again.";
  }

  async function api(path, { method = "GET", body } = {}) {
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
        signal: controller.signal,
        cache: "no-store",
      });
      const data = response.status === 204 ? null : await response.json();
      if (!response.ok) {
        throw new ApiError(
          data?.error?.message || "The request could not be completed.",
          data?.error?.code || "REQUEST_FAILED",
          data?.error?.details || [],
        );
      }
      return data;
    } catch (error) {
      if (error instanceof ApiError) throw error;
      const write = method !== "GET";
      if (error.name === "AbortError") {
        throw new ApiError(
          write
            ? "The request timed out and may have completed. Refresh your appointments or clinic schedule before trying again."
            : "The schedule is taking too long to respond. Please try again.",
          "TIMEOUT",
        );
      }
      throw new ApiError(
        write
          ? "The connection was interrupted and your change may have completed. Refresh your appointments or clinic schedule before trying again."
          : "Could not load the schedule. Check that the local server is running, then try again.",
        "NETWORK_ERROR",
      );
    } finally {
      window.clearTimeout(timeout);
    }
  }

  function localDate(date = new Date()) {
    return (
      date.getFullYear() +
      "-" +
      String(date.getMonth() + 1).padStart(2, "0") +
      "-" +
      String(date.getDate()).padStart(2, "0")
    );
  }

  function dateBounds(value) {
    if (!value) return {};
    const start = new Date(value + "T00:00:00");
    const end = new Date(start);
    end.setDate(end.getDate() + 1);
    return {
      starts_from: start.toISOString(),
      starts_before: end.toISOString(),
    };
  }

  function dateTime(value) {
    return dateFormat.format(new Date(value));
  }

  function timeRange(slot) {
    return (
      timeFormat.format(new Date(slot.starts_at)) +
      " – " +
      timeFormat.format(new Date(slot.ends_at))
    );
  }

  function currentClinic() {
    return clinicDetails.get(state.clinicId);
  }

  function statusPill(status) {
    const pill = node(
      "span",
      "status-pill",
      {
        confirmed: "Confirmed",
        cancelled: "Cancelled",
        available: "Available",
        booked: "Booked",
        expired: "Past",
      }[status] || status,
    );
    pill.dataset.status = status;
    return pill;
  }

  function empty(container, title, description, action) {
    const wrapper = node("div", "empty-state");
    wrapper.append(node("h3", "", title), node("p", "", description));
    if (action) wrapper.append(action);
    container.replaceChildren(wrapper);
  }

  function loading(container, message) {
    const wrapper = node("div", "loading-state", message);
    wrapper.setAttribute("role", "status");
    container.replaceChildren(wrapper);
  }

  function moreButton(id, page, label) {
    const element = $(id);
    element.hidden = !page.hasMore;
    element.disabled = page.loading || state.writeBusy;
    element.textContent = page.loading ? "Loading…" : label;
  }

  function syncControls() {
    $("confirm-booking").disabled = state.writeBusy || !state.selectedSlot;
    $("publish-slot").disabled = state.writeBusy || !state.clinicId;
    $("date-filter").disabled = state.writeBusy || !state.clinicId;
    $("clear-date").disabled = state.writeBusy || !state.clinicId;
    $("refresh-slots").disabled = state.writeBusy || !state.clinicId;
    $("clinic-select").disabled = state.writeBusy || !state.clinics.length;
    $("manage-clinic-select").disabled =
      state.writeBusy || !state.clinics.length;
  }

  function showView(view) {
    if (!["book", "bookings", "manage"].includes(view) || state.writeBusy)
      return;
    const changed = view !== state.view;
    if (changed) notice("");
    state.view = view;
    for (const name of ["book", "bookings", "manage"]) {
      $("view-" + name).hidden = name !== view;
    }
    for (const element of document.querySelectorAll("[data-view]")) {
      if (element.closest("nav")) {
        if (element.dataset.view === view)
          element.setAttribute("aria-current", "page");
        else element.removeAttribute("aria-current");
      }
    }
    if (view === "manage") {
      loadSlots("manage");
      loadBookings("clinic");
    }
    if (view === "book") loadSlots("available");
    if (view === "bookings" && state.lookupEmail) loadBookings("patient");
    const heading = $("view-" + view).querySelector("h1");
    if (heading) {
      heading.tabIndex = -1;
      heading.focus({ preventScroll: true });
    }
    if (changed) window.scrollTo({ top: 0, behavior: "instant" });
  }

  function updateSelection() {
    const summary = $("selection-details");
    summary.hidden = !$("booking-success").hidden;
    summary.replaceChildren();
    if (state.selectedSlot) {
      summary.append(
        node("span", "selection-label", "Your selected appointment"),
        node("h3", "", currentClinic()?.name || "Selected clinic"),
        node("p", "", dateTime(state.selectedSlot.starts_at)),
        node("strong", "selection-time", timeRange(state.selectedSlot)),
      );
    } else {
      summary.append(
        node("span", "selection-label", "Your appointment"),
        node("h3", "", "Choose a time to get started"),
        node(
          "p",
          "",
          "Your selected clinic and appointment time will appear here.",
        ),
      );
    }
    syncControls();
  }

  function chooseClinic(id) {
    state.clinicId = id || null;
    state.selectedSlot = null;
    for (const key of ["available", "manage", "clinic"]) versions[key]++;
    $("clinic-select").value = id || "";
    $("manage-clinic-select").value = id || "";
    $("clinic-address").textContent =
      currentClinic()?.address ||
      (id
        ? "Choose an available appointment below."
        : "Select a clinic to see its appointments.");
    try {
      if (id) sessionStorage.setItem("clinic-booking-clinic", id);
      else sessionStorage.removeItem("clinic-booking-clinic");
    } catch {
      // The application also works when browser storage is unavailable.
    }
    fieldError("booking-error");
    $("booking-success").hidden = true;
    $("booking-form").hidden = false;
    updateSelection();
    loadSlots("available");
    if (state.view === "manage") {
      loadSlots("manage");
      loadBookings("clinic");
    }
  }

  async function loadClinics(preferredId = state.clinicId) {
    const version = ++versions.clinics;
    $("clinic-select").disabled = true;
    $("manage-clinic-select").disabled = true;
    try {
      const clinics = [];
      let offset = 0;
      let more = true;
      // A bounded page loop avoids an unbounded fetch if a server misreports has_more.
      while (more && offset < 10000) {
        const page = await api(
          "/clinics?" + new URLSearchParams({ limit: 100, offset }),
        );
        if (version !== versions.clinics) return;
        clinics.push(...page.items);
        more = page.has_more;
        if (more && !page.items.length) {
          throw new ApiError(
            "The clinic list could not finish loading. Please retry.",
          );
        }
        offset += page.items.length;
      }
      if (more)
        throw new ApiError(
          "The clinic list is too large to load completely. Please contact the clinic.",
        );
      state.clinics = clinics;
      for (const clinic of clinics) clinicDetails.set(clinic.id, clinic);
      for (const select of [$("clinic-select"), $("manage-clinic-select")]) {
        select.replaceChildren();
        if (!clinics.length) select.append(new Option("No clinics yet", ""));
        for (const clinic of clinics) {
          select.append(
            new Option(
              clinic.name + (clinic.address ? " · " + clinic.address : ""),
              clinic.id,
            ),
          );
        }
      }
      let stored;
      try {
        stored = sessionStorage.getItem("clinic-booking-clinic");
      } catch {
        /* Optional. */
      }
      const requested = preferredId || stored;
      const selected =
        clinics.find((clinic) => clinic.id === requested) || clinics[0];
      chooseClinic(selected?.id || "");
      if (!clinics.length) $("clinic-create-panel").hidden = false;
    } catch (error) {
      if (version !== versions.clinics) return;
      notice(errorMessage(error), "error");
      empty(
        $("slot-list"),
        "We couldn’t load the clinics",
        "Try reconnecting to your local server.",
        button("Try again", "button button-secondary", () => loadClinics()),
      );
    } finally {
      if (version === versions.clinics) syncControls();
    }
  }

  function renderAvailable() {
    const container = $("slot-list");
    const page = pages.available;
    $("slot-count").textContent = page.items.length
      ? page.items.length +
        (page.hasMore ? "+" : "") +
        (page.items.length === 1 && !page.hasMore
          ? " available time"
          : " available times")
      : "No available times";
    if (!page.items.length) {
      empty(
        container,
        state.clinicId
          ? "No times available"
          : "Your first appointment starts here",
        state.clinicId
          ? $("date-filter").value
            ? "Try another date, or clear the date filter to see upcoming times."
            : "This clinic has no upcoming times available. Try another clinic or publish a time in Manage clinic."
          : "Create a clinic and publish appointment times in Manage clinic.",
        button(
          state.clinicId && $("date-filter").value
            ? "See all upcoming times"
            : "Manage clinic",
          "button button-secondary",
          () => {
            if (state.clinicId && $("date-filter").value) {
              $("date-filter").value = "";
              loadSlots("available");
            } else showView("manage");
          },
        ),
      );
      return;
    }
    container.replaceChildren();
    const days = new Map();
    for (const slot of page.items) {
      const day = localDate(new Date(slot.starts_at));
      if (!days.has(day)) days.set(day, []);
      days.get(day).push(slot);
    }
    for (const slots of days.values()) {
      const section = node("section", "slot-day");
      section.append(node("h3", "", dateTime(slots[0].starts_at)));
      const grid = node("div", "time-grid");
      for (const slot of slots) {
        const option = button("", "slot-option", () => {
          state.selectedSlot = slot;
          fieldError("booking-error");
          $("booking-success").hidden = true;
          $("booking-form").hidden = false;
          updateSelection();
          renderAvailable();
          if (window.matchMedia("(max-width: 780px)").matches) {
            $("booking-form").scrollIntoView({
              behavior: window.matchMedia("(prefers-reduced-motion: reduce)")
                .matches
                ? "auto"
                : "smooth",
              block: "start",
            });
            const nextField = $("patient-name").value.trim()
              ? $("patient-email")
              : $("patient-name");
            nextField.focus({ preventScroll: true });
          } else {
            container
              .querySelector('.slot-option[aria-pressed="true"]')
              ?.focus({ preventScroll: true });
          }
        });
        option.setAttribute(
          "aria-pressed",
          String(state.selectedSlot?.id === slot.id),
        );
        const minutes = Math.round(
          (new Date(slot.ends_at) - new Date(slot.starts_at)) / 60000,
        );
        option.setAttribute(
          "aria-label",
          dateTime(slot.starts_at) +
            ", " +
            timeRange(slot) +
            ", " +
            minutes +
            " minutes",
        );
        option.append(
          node(
            "strong",
            "slot-time",
            timeFormat.format(new Date(slot.starts_at)),
          ),
          node("span", "slot-duration", minutes + " min"),
        );
        grid.append(option);
      }
      section.append(grid);
      container.append(section);
    }
  }

  function renderManageSlots() {
    const container = $("manage-slot-list");
    if (!pages.manage.items.length) {
      empty(
        container,
        state.clinicId
          ? "No appointment times here yet"
          : "Choose or create a clinic",
        state.clinicId
          ? "Publish a time using the form, or change the status filter."
          : "Your clinic’s schedule will appear here.",
      );
      return;
    }
    container.replaceChildren();
    for (const slot of pages.manage.items) {
      const row = node("article", "schedule-row");
      const details = node("div", "appointment-info schedule-info");
      details.append(
        node("h3", "", dateTime(slot.starts_at)),
        node("p", "", timeRange(slot)),
      );
      row.append(details, statusPill(slot.availability));
      if (slot.status !== "cancelled") {
        const actions = node("div", "row-actions");
        if (slot.availability === "booked") {
          actions.append(node("span", "row-note", "Cancel its booking first"));
        } else {
          actions.append(
            button("Cancel time", "text-button danger-text", () => {
              confirmInline(
                actions,
                "Remove this time from the schedule?",
                async () => {
                  await writeAction(
                    null,
                    async () => {
                      await api("/slots/" + encodeURIComponent(slot.id), {
                        method: "DELETE",
                      });
                      if (state.selectedSlot?.id === slot.id) {
                        state.selectedSlot = null;
                        updateSelection();
                      }
                      notice("Appointment time cancelled.");
                      await refreshSchedules();
                    },
                    (error) => {
                      notice(errorMessage(error), "error");
                      loadSlots("manage");
                    },
                  );
                },
                () => renderManageSlots(),
              );
            }),
          );
        }
        row.append(actions);
      }
      container.append(row);
    }
  }

  async function loadSlots(kind, append = false) {
    const page = pages[kind];
    const version = ++versions[kind];
    const clinicId = state.clinicId;
    const container = $(
      kind === "available" ? "slot-list" : "manage-slot-list",
    );
    const moreId =
      kind === "available" ? "load-more-slots" : "load-more-manage-slots";
    if (!append) {
      page.items = [];
      page.hasMore = false;
    }
    if (!clinicId) {
      page.loading = false;
      if (kind === "available") renderAvailable();
      else renderManageSlots();
      moreButton(moreId, page, "Show more times");
      return true;
    }
    page.loading = true;
    if (!append) loading(container, "Loading appointment times…");
    moreButton(moreId, page, "Show more times");
    const params = { limit: PAGE_SIZE, offset: append ? page.items.length : 0 };
    if (kind === "available") {
      params.availability = "available";
      Object.assign(params, dateBounds($("date-filter").value));
    } else if ($("manage-status").value)
      params.availability = $("manage-status").value;
    try {
      const result = await api(
        "/clinics/" +
          encodeURIComponent(clinicId) +
          "/slots?" +
          new URLSearchParams(params),
      );
      if (version !== versions[kind] || clinicId !== state.clinicId)
        return false;
      page.items = append ? [...page.items, ...result.items] : result.items;
      page.hasMore = result.has_more;
      for (const slot of result.items) slotDetails.set(slot.id, slot);
      if (kind === "available") {
        // The selected time must remain in the freshly loaded availability snapshot.
        if (
          state.selectedSlot &&
          !append &&
          !page.items.some((slot) => slot.id === state.selectedSlot.id)
        ) {
          state.selectedSlot = null;
          updateSelection();
        }
        renderAvailable();
      } else renderManageSlots();
      return true;
    } catch (error) {
      if (version !== versions[kind] || clinicId !== state.clinicId)
        return false;
      if (kind === "available") {
        state.selectedSlot = null;
        updateSelection();
        $("slot-count").textContent = "Couldn’t load times";
      }
      empty(
        container,
        "Couldn’t load appointment times",
        errorMessage(error),
        button("Try again", "button button-secondary", () => loadSlots(kind)),
      );
      return false;
    } finally {
      if (version === versions[kind]) {
        page.loading = false;
        moreButton(moreId, page, "Show more times");
      }
    }
  }

  async function appointmentDetails(booking) {
    try {
      let slot = slotDetails.get(booking.slot_id);
      if (!slot) {
        slot = await api("/slots/" + encodeURIComponent(booking.slot_id));
        slotDetails.set(slot.id, slot);
      }
      let clinic = clinicDetails.get(slot.clinic_id);
      if (!clinic) {
        clinic = await api("/clinics/" + encodeURIComponent(slot.clinic_id));
        clinicDetails.set(clinic.id, clinic);
      }
      return { booking, slot, clinic };
    } catch (error) {
      return { booking, detailError: errorMessage(error) };
    }
  }

  function confirmInline(container, message, confirm, dismiss) {
    container.replaceChildren();
    const confirmation = node("div", "confirmation-actions");
    confirmation.append(
      node("p", "", message),
      button("Keep it", "button button-secondary", dismiss),
      button("Yes, cancel", "button button-danger", confirm),
    );
    container.append(confirmation);
    confirmation.querySelector("button").focus();
  }

  function renderBookings(kind) {
    const container = $(
      kind === "patient" ? "booking-list" : "clinic-booking-list",
    );
    const items = pages[kind].items;
    if (!items.length) {
      empty(
        container,
        kind === "patient" ? "No appointments found" : "No confirmed bookings",
        kind === "patient"
          ? "Check the email address you used, or book a new appointment."
          : "Bookings for the selected clinic will appear here.",
        kind === "patient"
          ? button("Book an appointment", "button button-secondary", () =>
              showView("book"),
            )
          : null,
      );
      return;
    }
    container.replaceChildren();
    for (const entry of items) {
      const { booking, slot, clinic, detailError } = entry;
      const row = node("article", "appointment-row");
      if (slot) {
        const date = new Date(slot.starts_at);
        const dateBadge = node("div", "appointment-date");
        dateBadge.setAttribute("aria-hidden", "true");
        dateBadge.append(
          node("strong", "", date.getDate()),
          node(
            "span",
            "",
            date.toLocaleDateString(undefined, { month: "short" }),
          ),
        );
        row.append(dateBadge);
      }
      const details = node("div", "appointment-info");
      details.append(node("h3", "", clinic?.name || "Appointment"));
      if (slot)
        details.append(
          node(
            "p",
            "appointment-time",
            dateTime(slot.starts_at) + " · " + timeRange(slot),
          ),
        );
      if (clinic?.address)
        details.append(node("p", "appointment-location", clinic.address));
      details.append(
        node("p", "appointment-patient", booking.patient_name || "Patient"),
      );
      if (kind === "clinic" && booking.patient_email) {
        details.append(node("p", "appointment-email", booking.patient_email));
      }
      if (detailError)
        details.append(
          node(
            "p",
            "field-error",
            "Time details could not be loaded. " + detailError,
          ),
        );
      row.append(details);
      const actions = node("div", "row-actions");
      actions.append(statusPill(booking.status));
      if (booking.status === "confirmed") {
        actions.append(
          button("Cancel appointment", "text-button danger-text", () => {
            confirmInline(
              actions,
              "Cancel this appointment? Its time will become available again.",
              async () => {
                await writeAction(
                  null,
                  async () => {
                    await api("/bookings/" + encodeURIComponent(booking.id), {
                      method: "DELETE",
                    });
                    if (state.lastBooking?.id === booking.id) {
                      $("booking-success").hidden = true;
                      $("booking-form").hidden = false;
                      state.lastBooking = null;
                      updateSelection();
                    }
                    notice(
                      "Appointment cancelled. Its time is available again if it has not started.",
                    );
                    await refreshSchedules();
                  },
                  (error) => {
                    notice(errorMessage(error), "error");
                    renderBookings(kind);
                  },
                );
              },
              () => renderBookings(kind),
            );
          }),
        );
      }
      row.append(actions);
      container.append(row);
    }
  }

  async function loadBookings(kind, append = false) {
    const version = ++versions[kind];
    const page = pages[kind];
    const container = $(
      kind === "patient" ? "booking-list" : "clinic-booking-list",
    );
    const moreId =
      kind === "patient" ? "load-more-bookings" : "load-more-clinic-bookings";
    const clinicId = state.clinicId;
    const email = state.lookupEmail;
    if (!append) {
      page.items = [];
      page.hasMore = false;
    }
    if ((kind === "patient" && !email) || (kind === "clinic" && !clinicId)) {
      page.loading = false;
      moreButton(moreId, page, "Show more appointments");
      if (kind === "clinic")
        empty(
          container,
          "Choose a clinic",
          "Confirmed appointments will appear here.",
        );
      return true;
    }
    page.loading = true;
    if (!append) loading(container, "Loading appointments…");
    moreButton(moreId, page, "Show more appointments");
    const params = { limit: PAGE_SIZE, offset: append ? page.items.length : 0 };
    if (kind === "patient") params.patient_email = email;
    else Object.assign(params, { clinic_id: clinicId, status: "confirmed" });
    try {
      const result = await api("/bookings?" + new URLSearchParams(params));
      const entries = await Promise.all(result.items.map(appointmentDetails));
      if (
        version !== versions[kind] ||
        (kind === "clinic" && clinicId !== state.clinicId) ||
        (kind === "patient" && email !== state.lookupEmail)
      )
        return false;
      page.items = append ? [...page.items, ...entries] : entries;
      page.hasMore = result.has_more;
      renderBookings(kind);
      return true;
    } catch (error) {
      if (version !== versions[kind]) return false;
      if (kind === "patient") fieldError("lookup-error", errorMessage(error));
      empty(
        container,
        "Couldn’t load appointments",
        errorMessage(error),
        button("Try again", "button button-secondary", () =>
          loadBookings(kind),
        ),
      );
      return false;
    } finally {
      if (version === versions[kind]) {
        page.loading = false;
        moreButton(moreId, page, "Show more appointments");
      }
    }
  }

  async function refreshSchedules() {
    const reads = [loadSlots("available")];
    if (state.view === "manage")
      reads.push(loadSlots("manage"), loadBookings("clinic"));
    if (state.lookupEmail) reads.push(loadBookings("patient"));
    await Promise.all(reads);
  }

  async function writeAction(form, operation, onError) {
    if (state.writeBusy) return;
    notice("");
    state.writeBusy = true;
    const controls = [
      ...document.querySelectorAll("button, select, input"),
    ].map((element) => ({
      element,
      disabled: element.disabled,
    }));
    controls.forEach(({ element }) => {
      element.disabled = true;
    });
    if (form) form.setAttribute("aria-busy", "true");
    try {
      await operation();
    } catch (error) {
      if (onError) onError(error);
      else notice(errorMessage(error), "error");
    } finally {
      state.writeBusy = false;
      controls.forEach(({ element, disabled }) => {
        element.disabled = disabled;
      });
      if (form) form.setAttribute("aria-busy", "false");
      syncControls();
      moreButton("load-more-slots", pages.available, "Show more times");
      moreButton("load-more-manage-slots", pages.manage, "Show more times");
      moreButton("load-more-bookings", pages.patient, "Show more appointments");
      moreButton(
        "load-more-clinic-bookings",
        pages.clinic,
        "Show more appointments",
      );
    }
  }

  function bookingSuccess(booking, slot, clinic) {
    const success = $("booking-success");
    const icon = node("span", "success-icon");
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("aria-hidden", "true");
    svg.setAttribute("fill", "none");
    svg.setAttribute("stroke", "currentColor");
    svg.setAttribute("stroke-width", "2");
    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    path.setAttribute("d", "m5 12 4 4L19 6");
    svg.append(path);
    icon.append(svg);
    success.replaceChildren(
      icon,
      node("h3", "", "Your appointment is confirmed"),
      node(
        "p",
        "",
        (clinic?.name || "Your clinic") + " · " + dateTime(slot.starts_at),
      ),
      node("strong", "selection-time", timeRange(slot)),
      node("p", "", "Booked for " + booking.patient_name + "."),
      button("View my appointments", "button", () => showView("bookings")),
      button("Book another appointment", "text-button", () => {
        success.hidden = true;
        $("booking-form").hidden = false;
        state.selectedSlot = null;
        updateSelection();
        loadSlots("available");
      }),
    );
    success.hidden = false;
    success.setAttribute("role", "status");
    $("booking-form").hidden = true;
    $("selection-details").hidden = true;
  }

  async function submitBooking(event) {
    event.preventDefault();
    const form = event.currentTarget;
    fieldError("booking-error");
    if (!form.reportValidity()) return;
    const slot = state.selectedSlot;
    const clinic = currentClinic();
    if (!slot) {
      fieldError(
        "booking-error",
        "Choose an available appointment time first.",
      );
      return;
    }
    const patientName = $("patient-name").value.trim();
    const patientEmail = $("patient-email").value.trim();
    if (!patientName) {
      fieldError("booking-error", "Enter the patient’s name.");
      $("patient-name").focus();
      return;
    }
    await writeAction(
      form,
      async () => {
        const booking = await api("/bookings", {
          method: "POST",
          body: {
            slot_id: slot.id,
            patient_name: patientName,
            patient_email: patientEmail,
          },
        });
        state.lastBooking = booking;
        state.lookupEmail = booking.patient_email;
        $("lookup-email").value = booking.patient_email;
        state.selectedSlot = null;
        updateSelection();
        bookingSuccess(booking, slot, clinic);
        notice("");
        await loadSlots("available");
      },
      (error) => {
        fieldError("booking-error", errorMessage(error));
        if (
          [
            "SLOT_ALREADY_BOOKED",
            "SLOT_CANCELLED",
            "SLOT_STARTED",
            "SLOT_NOT_FOUND",
          ].includes(error.code)
        ) {
          state.selectedSlot = null;
          updateSelection();
          loadSlots("available");
        }
      },
    );
  }

  async function submitClinic(event) {
    event.preventDefault();
    const form = event.currentTarget;
    fieldError("clinic-error");
    if (!form.reportValidity()) return;
    const name = $("clinic-name").value.trim();
    const address = $("clinic-address-input").value.trim();
    if (!name) {
      fieldError("clinic-error", "Enter the clinic’s name.");
      return;
    }
    await writeAction(
      form,
      async () => {
        const clinic = await api("/clinics", {
          method: "POST",
          body: { name, ...(address ? { address } : {}) },
        });
        form.reset();
        $("clinic-create-panel").hidden = true;
        notice(
          clinic.name + " is ready. Publish its first appointment time below.",
        );
        await loadClinics(clinic.id);
      },
      (error) => fieldError("clinic-error", errorMessage(error)),
    );
  }

  async function submitSlot(event) {
    event.preventDefault();
    const form = event.currentTarget;
    fieldError("slot-error");
    if (!form.reportValidity()) return;
    if (!state.clinicId) {
      fieldError("slot-error", "Create or select a clinic first.");
      return;
    }
    const day = $("slot-date").value;
    const startText = $("slot-start").value;
    const endText = $("slot-end").value;
    const start = new Date(day + "T" + startText);
    const end = new Date(day + "T" + endText);
    if (
      !Number.isFinite(start.getTime()) ||
      !Number.isFinite(end.getTime()) ||
      localDate(start) !== day ||
      timeValue(start) !== startText ||
      timeValue(end) !== endText
    ) {
      fieldError(
        "slot-error",
        "Enter a valid local date and time. This time may not exist because of daylight saving.",
      );
      return;
    }
    if (start <= new Date()) {
      fieldError("slot-error", "Choose a start time in the future.");
      return;
    }
    if (end <= start) {
      fieldError(
        "slot-error",
        "End time must be after start time on the selected date.",
      );
      return;
    }
    const clinicId = state.clinicId;
    await writeAction(
      form,
      async () => {
        await api("/clinics/" + encodeURIComponent(clinicId) + "/slots", {
          method: "POST",
          body: { starts_at: start.toISOString(), ends_at: end.toISOString() },
        });
        notice(
          "Appointment time published: " +
            dateTime(start) +
            ", " +
            timeFormat.format(start) +
            ".",
        );
        await refreshSchedules();
      },
      (error) => fieldError("slot-error", errorMessage(error)),
    );
  }

  function timeValue(date) {
    return (
      String(date.getHours()).padStart(2, "0") +
      ":" +
      String(date.getMinutes()).padStart(2, "0")
    );
  }

  function initialize() {
    const tomorrow = new Date();
    tomorrow.setDate(tomorrow.getDate() + 1);
    $("slot-date").min = localDate();
    $("slot-date").value = localDate(tomorrow);
    $("slot-start").value = "09:00";
    $("slot-end").value = "09:30";
    $("date-filter").min = localDate();
    $("timezone-label").textContent = Intl.DateTimeFormat()
      .resolvedOptions()
      .timeZone.replaceAll("_", " ");
    document.addEventListener("click", (event) => {
      const control = event.target.closest("[data-view]");
      if (control) showView(control.dataset.view);
    });
    $("clinic-select").addEventListener("change", (event) =>
      chooseClinic(event.target.value),
    );
    $("manage-clinic-select").addEventListener("change", (event) =>
      chooseClinic(event.target.value),
    );
    $("date-filter").addEventListener("change", () => {
      state.selectedSlot = null;
      updateSelection();
      loadSlots("available");
    });
    $("clear-date").addEventListener("click", () => {
      $("date-filter").value = "";
      loadSlots("available");
    });
    $("refresh-slots").addEventListener("click", () => loadSlots("available"));
    $("manage-status").addEventListener("change", () => loadSlots("manage"));
    $("load-more-slots").addEventListener("click", () =>
      loadSlots("available", true),
    );
    $("load-more-manage-slots").addEventListener("click", () =>
      loadSlots("manage", true),
    );
    $("load-more-bookings").addEventListener("click", () =>
      loadBookings("patient", true),
    );
    $("load-more-clinic-bookings").addEventListener("click", () =>
      loadBookings("clinic", true),
    );
    $("booking-form").addEventListener("submit", submitBooking);
    $("clinic-form").addEventListener("submit", submitClinic);
    $("slot-form").addEventListener("submit", submitSlot);
    $("lookup-form").addEventListener("submit", (event) => {
      event.preventDefault();
      fieldError("lookup-error");
      if (!event.currentTarget.reportValidity()) return;
      state.lookupEmail = $("lookup-email").value.trim();
      loadBookings("patient");
    });
    $("new-clinic-button").addEventListener("click", () => {
      $("clinic-create-panel").hidden = false;
      $("clinic-name").focus();
    });
    $("create-clinic-cancel").addEventListener("click", () => {
      $("clinic-create-panel").hidden = true;
      fieldError("clinic-error");
    });
    for (const [formId, errorId] of [
      ["booking-form", "booking-error"],
      ["clinic-form", "clinic-error"],
      ["slot-form", "slot-error"],
      ["lookup-form", "lookup-error"],
    ]) {
      $(formId).addEventListener("input", () => fieldError(errorId));
    }
    updateSelection();
    loadClinics();
  }

  if (document.readyState === "loading")
    document.addEventListener("DOMContentLoaded", initialize, { once: true });
  else initialize();
})();
