/* Viewer controls, trusted-HTML tooltips, and source-backed details. */
(() => {
    'use strict';
    const tooltip = document.createElement('div');
    tooltip.id = 'custom-vis-tooltip';
    document.body.appendChild(tooltip);
    let dialog, appearanceNetwork, previousFocus;
    let tooltipPoint = {x: 0, y: 0};
    const htmlFields = new Set(['name', 'ancestry', 'class', 'notes', 'details',
        'physical_description', 'personality', 'other_details', 'description']);
    const labels = {name: 'Name', ancestry: 'Ancestry', class: 'Class',
        physical_description: 'Physical description', personality: 'Personality',
        other_details: 'Other details', notes: 'Notes', details: 'Details',
        location: 'Room', group: 'Group', from: 'From room', to: 'To room',
        status: 'Status', direction: 'Direction',
        description: 'Description', line_style: 'Line style'};
    const fieldOrder = ['name', 'ancestry', 'class', 'notes', 'details', 'physical_description',
        'personality', 'other_details', 'location', 'group', 'from', 'to', 'status', 'direction'];
    const hiddenFields = new Set(['images', 'color', 'shape', 'display_color',
        'id', 'position', 'defaultPosition']);

    function hideTooltip() { tooltip.style.visibility = 'hidden'; }
    function positionTooltip() {
        const rect = tooltip.getBoundingClientRect();
        const x = tooltipPoint.x + 18 + rect.width > innerWidth - 8
            ? tooltipPoint.x - rect.width - 12 : tooltipPoint.x + 18;
        const y = tooltipPoint.y + 18 + rect.height > innerHeight - 8
            ? tooltipPoint.y - rect.height - 12 : tooltipPoint.y + 18;
        tooltip.style.left = Math.max(8, Math.min(x, innerWidth - rect.width - 8)) + 'px';
        tooltip.style.top = Math.max(8, Math.min(y, innerHeight - rect.height - 8)) + 'px';
    }
    function imageFallback(img, callback = () => {}) {
        img.addEventListener('error', () => {
            const fallback = document.createElement('span');
            fallback.textContent = 'Image unavailable';
            fallback.className = 'map-image-unavailable';
            img.replaceWith(fallback);
            callback();
        }, {once: true});
    }
    function showTooltip(html, event) {
        if (!html || dialog?.open) { hideTooltip(); return; }
        tooltip.innerHTML = html.replace(/\n/g, '<br>');
        tooltipPoint = {x: event.clientX ?? event.pageX, y: event.clientY ?? event.pageY};
        tooltip.querySelectorAll('img').forEach(img => {
            img.addEventListener('load', positionTooltip, {once: true});
            imageFallback(img, positionTooltip);
        });
        tooltip.style.visibility = 'visible';
        positionTooltip();
    }
    function setCharacterVisibility(visibility) {
        const tooltipProperty = 'tooltip_' + visibility;
        nodes.update(nodes.get().map(node => {
            if (node.node_type === 'character') return {id: node.id, hidden: visibility !== 'show_all'};
            if (node.node_type === 'character_group') return {id: node.id, hidden: visibility === 'hidden', title: node[tooltipProperty]};
            if (node.node_type === 'room') return {id: node.id, hidden: false, title: node[tooltipProperty]};
            return {id: node.id, hidden: false};
        }));
        hideTooltip();
    }
    function setupCharacterVisibility() {
        const toolbar = document.createElement('div');
        toolbar.id = 'map-toolbar';
        toolbar.innerHTML = `<label for="character-visibility">Character Visibility
            <select id="character-visibility" aria-label="Character Visibility">
              <option value="hidden">Hidden</option><option value="groups_only" selected>Groups Only</option>
              <option value="show_all">Show All</option>
            </select></label>
            <div id="map-build-info"><div id="program-version"></div><div id="build-date"></div></div>`;
        const graph = document.getElementById('mynetwork');
        graph.before(toolbar);
        function sizeGraph() {
            const view = {position: network.getViewPosition(), scale: network.getScale()};
            const height = Math.max(240, innerHeight - toolbar.getBoundingClientRect().height - 4);
            network.setSize('100%', height + 'px');
            network.moveTo({...view, animation: false});
        }
        sizeGraph();
        addEventListener('resize', sizeGraph);
        document.getElementById('program-version').textContent = 'Version ' + PF2E_MAP_TRACKER_BUILD.version;
        document.getElementById('build-date').textContent = 'Built ' + PF2E_MAP_TRACKER_BUILD.builtAt;
        const select = document.getElementById('character-visibility');
        select.addEventListener('change', event => setCharacterVisibility(event.target.value));
        setCharacterVisibility(select.value);
        graph.tabIndex = 0;
        graph.setAttribute('aria-label', 'Map graph');
    }
    function appendField(container, key, value, reference) {
        if (value == null || (typeof value === 'string' && !value.trim())) return;
        const dl = document.createElement('dl');
        dl.className = 'map-detail-field';
        const dt = document.createElement('dt');
        dt.textContent = labels[key] || key;
        const dd = document.createElement('dd');
        if (reference) {
            const name = document.createElement('span');
            name.innerHTML = reference;
            dd.append(name);
        } else if (htmlFields.has(key)) dd.innerHTML = String(value).replace(/\n/g, '<br>');
        else if (typeof value === 'object') dd.textContent = JSON.stringify(value);
        else dd.textContent = String(value);
        if (!dd.textContent.trim() && !dd.querySelector('img,video,audio,iframe,svg,canvas,object,embed')) return;
        dl.append(dt, dd);
        container.append(dl);
    }
    function renderAppearance(appearance) {
        const container = document.getElementById('map-detail-appearance');
        container.replaceChildren();
        if (appearance.shape) {
            const shape = document.createElement('div');
            shape.className = 'map-shape-preview';
            shape.setAttribute('role', 'img');
            shape.setAttribute('aria-label', 'Shape: ' + appearance.shape);
            container.append(shape);
            // This vis-network version leaves margins undefined for numeric zero.
            // Explicit sides keep label-sized shapes drawable without visible labels.
            appearanceNetwork = new vis.Network(shape, {nodes: [{id: 1,
                x: 0, y: 0, label: appearance.shape === 'text' ? 'Aa' : '', shape: appearance.shape,
                color: appearance.color, font: {color: appearance.color},
                margin: {top: 0, right: 0, bottom: 0, left: 0},
                widthConstraint: {minimum: 32}, heightConstraint: {minimum: 24}}], edges: []},
            {physics: false, interaction: {dragNodes: false, dragView: false, zoomView: false,
                selectable: false, keyboard: false}, layout: {improvedLayout: false}});
            appearanceNetwork.fit({animation: false});
            shape.querySelector('.vis-network')?.setAttribute('tabindex', '-1');
        } else {
            const line = document.createElement('div');
            line.className = 'map-line-preview';
            line.setAttribute('role', 'img');
            line.setAttribute('aria-label', 'Connection appearance');
            line.style.color = appearance.color;
            if (appearance.direction !== 'forward_only') line.append(document.createTextNode('◀'));
            const stroke = document.createElement('span');
            stroke.style.borderTopStyle = appearance.line_style;
            line.append(stroke);
            if (appearance.direction !== 'backward_only') line.append(document.createTextNode('▶'));
            container.append(line);
        }
    }
    function renderGallery(images) {
        const gallery = document.getElementById('map-detail-gallery');
        gallery.hidden = images.length === 0;
        const thumbnails = document.getElementById('map-gallery-thumbnails');
        thumbnails.hidden = images.length <= 1;
        thumbnails.replaceChildren();
        const metadata = document.getElementById('map-image-metadata');
        function selectImage(index) {
            const picture = images[index];
            const image = document.getElementById('map-detail-image');
            const fallback = document.getElementById('map-image-fallback');
            image.hidden = false;
            fallback.hidden = true;
            image.onload = () => { image.hidden = false; fallback.hidden = true; };
            image.onerror = () => { image.hidden = true; fallback.hidden = false; };
            image.alt = picture.alt || `Image ${index + 1}`;
            image.src = picture.url;
            const caption = document.getElementById('map-detail-caption');
            caption.textContent = picture.caption;
            caption.hidden = !picture.caption.trim();
            metadata.replaceChildren();
            appendField(metadata, 'Source', picture.src);
            appendField(metadata, 'Alt text', picture.alt);
            thumbnails.querySelectorAll('button').forEach((button, i) => button.setAttribute('aria-pressed', String(i === index)));
        }
        images.forEach((picture, index) => {
            const button = document.createElement('button');
            button.type = 'button';
            button.setAttribute('aria-label', `Show image ${index + 1}`);
            const img = document.createElement('img');
            img.alt = picture.alt || `Image ${index + 1}`;
            imageFallback(img);
            img.src = picture.url;
            button.append(img);
            button.addEventListener('click', () => selectImage(index));
            thumbnails.append(button);
        });
        if (images.length) selectImage(0);
    }
    function setupDetails() {
        dialog = document.createElement('dialog');
        dialog.id = 'map-details';
        dialog.setAttribute('aria-labelledby', 'map-detail-title');
        dialog.innerHTML = `<div class="map-dialog-header"><div class="map-dialog-heading"><div id="map-detail-kind"></div>
            <h2 id="map-detail-title"></h2></div><div class="map-dialog-actions"><div id="map-detail-appearance"></div>
            <button id="map-detail-close" type="button" autofocus>Close</button></div></div>
            <div class="map-dialog-body"><section aria-label="Object information">
            <div id="map-detail-fields"></div></section><section id="map-detail-gallery" aria-label="Pictures">
            <figure id="map-detail-figure"><img id="map-detail-image" alt=""><div id="map-image-fallback" hidden>Image unavailable</div>
            <figcaption id="map-detail-caption"></figcaption></figure><div id="map-gallery-thumbnails"></div>
            <div id="map-image-metadata" class="map-image-metadata"></div></section></div>`;
        document.body.append(dialog);
        document.getElementById('map-detail-close').addEventListener('click', () => dialog.close());
        dialog.addEventListener('keydown', event => {
            if (event.key !== 'Tab') return;
            const focusable = Array.from(dialog.querySelectorAll(
                'button:not([disabled]),a[href],input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])'
            )).filter(element => element.getClientRects().length > 0);
            if (!focusable.length) { event.preventDefault(); return; }
            const current = focusable.indexOf(document.activeElement);
            const next = current < 0 ? (event.shiftKey ? focusable.length - 1 : 0)
                : (current + (event.shiftKey ? -1 : 1) + focusable.length) % focusable.length;
            event.preventDefault();
            focusable[next].focus();
        });
        dialog.addEventListener('click', event => {
            const bounds = dialog.getBoundingClientRect();
            if (event.target === dialog && (event.clientX < bounds.left || event.clientX > bounds.right
                || event.clientY < bounds.top || event.clientY > bounds.bottom)) dialog.close();
        });
        dialog.addEventListener('close', () => {
            appearanceNetwork?.destroy(); appearanceNetwork = null;
            network.setOptions({interaction: {keyboard: viewerKeyboard}});
            previousFocus?.focus({preventScroll: true});
        });
        const viewerKeyboard = network.interactionHandler.options.keyboard.enabled;
        network.on('click', params => {
            const nodeId = network.getNodeAt(params.pointer.DOM);
            const object = nodeId !== undefined ? nodes.get(nodeId) : edges.get(network.getEdgeAt(params.pointer.DOM));
            if (!object?.detail) return;
            const detail = object.detail;
            hideTooltip();
            appearanceNetwork?.destroy(); appearanceNetwork = null;
            document.getElementById('map-detail-title').innerHTML = detail.title;
            document.getElementById('map-detail-kind').textContent = detail.kind.replace(/_/g, ' ');
            const fields = document.getElementById('map-detail-fields');
            fields.replaceChildren();
            const keys = [...fieldOrder.filter(key => key in detail.fields),
                ...Object.keys(detail.fields).filter(key => !fieldOrder.includes(key))];
            for (const key of keys) {
                if (!hiddenFields.has(key)) appendField(fields, key, detail.fields[key], detail.references[key]);
            }
            if (detail.members?.length) appendField(fields, 'Members', detail.members.join(', '));
            if (detail.occupants?.length) appendField(fields, 'Occupants', detail.occupants.join(', '));
            renderGallery(detail.images);
            dialog.querySelector('.map-dialog-body').classList.toggle('has-images', detail.images.length > 0);
            previousFocus = document.activeElement;
            network.setOptions({interaction: {keyboard: false}});
            if (!dialog.open) dialog.showModal();
            dialog.scrollTop = 0;
            renderAppearance(detail.appearance);
        });
    }
    function setupCustomTooltips() {
        network.on('hoverNode', params => showTooltip(nodes.get(params.node)?.title, params.event));
        network.on('hoverEdge', params => showTooltip(edges.get(params.edge)?.title, params.event));
        for (const event of ['blurNode', 'blurEdge', 'dragStart', 'zoom']) network.on(event, hideTooltip);
        addEventListener('resize', hideTooltip);
        addEventListener('scroll', hideTooltip, true);
    }
    function setup() {
        if (!window.network || !window.nodes || !window.edges) { setTimeout(setup, 100); return; }
        setupCharacterVisibility();
        setupDetails();
        setupCustomTooltips();
        if (PF2E_MAP_TRACKER_DEFAULT_VIEW) network.moveTo({...PF2E_MAP_TRACKER_DEFAULT_VIEW, animation: false});
    }
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', setup);
    else setup();
})();
