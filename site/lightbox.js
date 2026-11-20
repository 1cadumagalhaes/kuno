// Enlarges the product screenshots in a native modal dialog.
// Focus, Esc, the top layer and focus return are the browser's job; the only
// additions here are the click-to-enlarge affordance and the caption swap.
const labels = Object.assign({ expandImage: "Enlarge image", closeImage: "Close image" }, window.KUNO_I18N || {});

const dialog = document.createElement("dialog");
dialog.className = "shot-dialog";
dialog.setAttribute("closedby", "any");

const viewer = document.createElement("figure");
const viewport = document.createElement("div");
viewport.className = "shot-viewport";
const viewerImage = document.createElement("img");
const viewerCaption = document.createElement("figcaption");
viewport.append(viewerImage);
viewer.append(viewport, viewerCaption);

const closeButton = document.createElement("button");
closeButton.type = "button";
closeButton.className = "shot-close";
closeButton.setAttribute("aria-label", labels.closeImage);
closeButton.innerHTML = '<svg viewBox="0 0 16 16" aria-hidden="true" focusable="false"><path d="M3 3l10 10M13 3L3 13" /></svg>';
closeButton.addEventListener("click", () => dialog.close());

dialog.append(viewer, closeButton);
document.body.append(dialog);

// Backdrop click, for browsers without the closedby attribute.
dialog.addEventListener("click", (event) => {
  if (event.target === dialog) dialog.close();
});

for (const image of document.querySelectorAll(".screen-shot img, .log-strip img, .hero-shot img")) {
  const trigger = document.createElement("button");
  trigger.type = "button";
  trigger.className = "shot-open";
  trigger.setAttribute("aria-label", `${labels.expandImage}: ${image.alt}`);
  image.replaceWith(trigger);
  trigger.append(image);
  trigger.addEventListener("click", () => {
    viewerImage.src = image.currentSrc || image.src;
    viewerImage.alt = image.alt;
    // These SVGs carry no width/height of their own, so inherit the source's
    // declared size to keep the aspect ratio before the file loads.
    for (const dimension of ["width", "height"]) {
      const value = image.getAttribute(dimension);
      if (value) viewerImage.setAttribute(dimension, value);
    }
    viewerCaption.textContent = image.closest("figure")?.querySelector("figcaption")?.textContent ?? image.alt;
    dialog.showModal();
  });
}
