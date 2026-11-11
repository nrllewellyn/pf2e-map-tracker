/* Viewer controls, trusted-HTML tooltips, and source-backed details. */
(() => {
    'use strict';
    const {hasContent, appendDetailField, createSignCard, renderRoomSigns} = window.MapDetails;
    const tooltip = document.createElement('div');
    tooltip.id = 'custom-vis-tooltip';
    document.body.appendChild(tooltip);
    let dialog, additionalDialog, npcGroupDialog, imagePreview, appearanceNetwork, previousFocus, viewerKeyboard;
    const npcGroups = new Map(PF2E_MAP_TRACKER_NPC_GROUPS.map(group => [group.id, group]));
    const pictureTimers = new Map();
    const npcGroupSummaryFields = ['language', 'language_visual_style', 'signage_physical_form', 'communication_quirks'];
    const npcGroupDetailFields = ['language', 'language_visual_style', 'language_oddities',
        'signage_physical_form', 'communication_quirks', 'known_ancestries', 'common_appearance', 'demeanor'];
    let tooltipPoint = {x: 0, y: 0};
    const htmlFields = new Set(['name', 'ancestry', 'class', 'short_description', 'details',
        'physical_description', 'personality', 'other_details', ...npcGroupDetailFields]);
    const labels = {name: 'Name', ancestry: 'Ancestry', class: 'Class',
        physical_description: 'Physical description', personality: 'Personality',
        other_details: 'Other details', details: 'Details',
        location: 'Room', group: 'Group', from: 'From room', to: 'To room',
        status: 'Status', direction: 'Direction',
        line_style: 'Line style',
        language: 'Language', language_visual_style: 'Lettering', language_oddities: 'Language Oddities',
        signage_physical_form: 'Signage Form',
        communication_quirks: 'Communication Quirks', known_ancestries: 'Known Ancestries',
        common_appearance: 'Common Appearance', demeanor: 'Demeanor'};
    const fieldOrder = ['short_description', 'name', 'ancestry', 'class', 'details', 'physical_description',
        'personality', 'other_details', 'location', 'group', 'from', 'to', 'status', 'direction'];
    const hiddenFields = new Set(['images', 'color', 'shape', 'display_color',
        'id', 'position', 'defaultPosition', 'signs']);

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
        if (!html || dialog?.open || additionalDialog?.open || npcGroupDialog?.open) { hideTooltip(); return; }
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
              <option value="hidden">Hidden</option><option value="groups_only">Groups Only</option>
              <option value="show_all" selected>Show All</option>
            </select></label>
            <button id="map-additional-open" type="button" aria-haspopup="dialog">Additional Information</button>
            <div id="map-build-info"><div id="program-version"></div><div id="build-date"></div></div>`;
        const graph = document.getElementById('mynetwork');
        graph.before(toolbar);
        function sizeGraph() {
            const view = {position: network.getViewPosition(), scale: network.getScale()};
            network.setSize(graph.clientWidth + 'px', graph.clientHeight + 'px');
            network.moveTo({...view, animation: false});
        }
        document.getElementById('program-version').textContent = 'Version ' + PF2E_MAP_TRACKER_BUILD.version;
        document.getElementById('build-date').textContent = 'Built ' + PF2E_MAP_TRACKER_BUILD.builtAt;
        sizeGraph();
        addEventListener('resize', sizeGraph);
        const select = document.getElementById('character-visibility');
        select.addEventListener('change', event => setCharacterVisibility(event.target.value));
        setCharacterVisibility(select.value);
        graph.tabIndex = 0;
        graph.setAttribute('aria-label', 'Map graph');
    }
    function trapDialogFocus(event, modal) {
        if (event.key !== 'Tab') return;
        const focusable = Array.from(modal.querySelectorAll(
            'button:not([disabled]),summary,a[href],input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])'
        )).filter(element => element.getClientRects().length > 0);
        event.preventDefault();
        if (!focusable.length) return;
        const current = focusable.indexOf(document.activeElement);
        const next = current < 0 ? (event.shiftKey ? focusable.length - 1 : 0)
            : (current + (event.shiftKey ? -1 : 1) + focusable.length) % focusable.length;
        focusable[next].focus();
    }
    function dismissOnBackdrop(event, modal) {
        const bounds = modal.getBoundingClientRect();
        if (event.target === modal && (event.clientX < bounds.left || event.clientX > bounds.right
            || event.clientY < bounds.top || event.clientY > bounds.bottom)) modal.close();
    }
    function restoreViewerKeyboard() {
        network.setOptions({interaction: {
            keyboard: dialog.open || additionalDialog?.open || npcGroupDialog?.open ? false : viewerKeyboard
        }});
    }
    function appendField(container, key, value, reference) {
        if (value == null || (typeof value === 'string' && !value.trim())) return;
        const renderValue = dd => {
            if (reference) {
                const name = document.createElement('span');
                name.innerHTML = reference;
                dd.append(name);
            } else if (htmlFields.has(key)) dd.innerHTML = String(value).replace(/\n/g, '<br>');
            else if (typeof value === 'object') dd.textContent = JSON.stringify(value);
            else dd.textContent = String(value);
        };
        if (key === 'short_description') {
            const description = document.createElement('div');
            description.className = 'map-short-description';
            renderValue(description);
            if (hasContent(description)) container.append(description);
        } else appendDetailField(container, labels[key] || key, renderValue);
    }
    function appendRoomDetails(container, html) {
        if (!/<map-sign[\s/>]/i.test(html)) {
            appendField(container, 'details', html);
            return;
        }
        appendDetailField(container, labels.details, dd => {
            dd.innerHTML = html;
            if (renderRoomSigns(dd, npcGroups, viewerSignCard) === null) {
                dd.innerHTML = html.replace(/\n/g, '<br>');
            }
        });
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
        document.getElementById('map-image-details').open = false;
        const metadata = document.getElementById('map-image-metadata');
        function selectImage(index) {
            const picture = images[index];
            const image = document.getElementById('map-detail-image');
            const openImage = document.getElementById('map-detail-image-open');
            const fallback = document.getElementById('map-image-fallback');
            openImage.hidden = false;
            image.hidden = false;
            fallback.hidden = true;
            image.onload = () => { openImage.hidden = false; image.hidden = false; fallback.hidden = true; };
            image.onerror = () => { openImage.hidden = true; image.hidden = true; fallback.hidden = false; };
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
    function clearPictureTimers(owner) {
        (pictureTimers.get(owner) || []).forEach(clearInterval);
        pictureTimers.delete(owner);
    }
    function rotatingPicture(images, owner, title) {
        if (!images.length) return null;
        const figure = document.createElement('figure');
        figure.className = 'map-rotating-picture';
        const img = document.createElement('img');
        const fallback = document.createElement('span');
        fallback.className = 'map-image-unavailable';
        fallback.textContent = 'Image unavailable';
        let index = 0;
        function showPicture() {
            const picture = images[index];
            img.hidden = false;
            fallback.hidden = true;
            img.onload = () => { img.hidden = false; fallback.hidden = true; };
            img.onerror = () => { img.hidden = true; fallback.hidden = false; };
            img.alt = picture.alt || title;
            img.title = picture.caption || title;
            img.src = picture.url;
        }
        figure.append(img, fallback);
        showPicture();
        if (images.length > 1 && !matchMedia('(prefers-reduced-motion: reduce)').matches) {
            const timer = setInterval(() => {
                if (!owner.open || document.hidden) return;
                index = (index + 1) % images.length;
                showPicture();
            }, 4500);
            pictureTimers.set(owner, [...pictureTimers.get(owner) || [], timer]);
        }
        return figure;
    }
    function groupButton(group, className = '') {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = className;
        button.innerHTML = group.name;
        button.setAttribute('aria-haspopup', 'dialog');
        button.addEventListener('click', () => showNpcGroupDetails(group));
        return button;
    }
    function viewerSignCard(sign, group, index) {
        return createSignCard(document, sign, index, {
            groupName: group && groupButton(group),
            language: group?.language,
            thumbnail: group && rotatingPicture(group.example_sign_images, dialog, 'Example sign'),
        });
    }
    function renderConnectionSigns(signs, container, references) {
        if (!signs?.length) return;
        const section = document.createElement('section');
        section.className = 'map-signs';
        const heading = document.createElement('h3');
        heading.textContent = 'Signs';
        section.append(heading);
        signs.forEach((sign, index) => {
            const endpoint = {source: 'from', destination: 'to'}[sign.side];
            const room = references[endpoint];
            section.append(viewerSignCard({
                location: room ? `Entrance from ${room}` : '',
                description: sign.description.replace(/\n/g, '<br>'),
                translation: sign.translation.replace(/\n/g, '<br>'),
            }, npcGroups.get(sign.group), index));
        });
        container.append(section);
    }
    function renderNpcGroupPictures(container, title, images) {
        if (!images.length) return;
        const section = document.createElement('section');
        const heading = document.createElement('h4');
        heading.textContent = title;
        const gallery = document.createElement('div');
        gallery.className = 'map-npc-group-gallery';
        images.forEach((picture, index) => {
            const figure = document.createElement('figure');
            const button = document.createElement('button');
            button.type = 'button';
            button.setAttribute('aria-label', `View ${title.toLowerCase()} image ${index + 1} full screen`);
            const img = document.createElement('img');
            img.alt = picture.alt || `${title} ${index + 1}`;
            imageFallback(img);
            img.src = picture.url;
            button.append(img);
            button.addEventListener('click', () => openImagePreview(picture.url, img.alt));
            const caption = document.createElement('figcaption');
            caption.textContent = picture.caption;
            caption.hidden = !picture.caption.trim();
            figure.append(button, caption);
            gallery.append(figure);
        });
        section.append(heading, gallery);
        container.append(section);
    }
    function showNpcGroupDetails(group) {
        hideTooltip();
        const container = document.getElementById('map-npc-group-content');
        container.replaceChildren();
        document.getElementById('map-npc-group-title').innerHTML = group.name;
        const fields = document.createElement('div');
        fields.id = 'map-npc-group-fields';
        npcGroupDetailFields.forEach(key => appendField(fields, key,
            Array.isArray(group[key]) ? group[key].join(', ') : group[key]));
        container.append(fields);
        renderNpcGroupPictures(container, 'Example signs', group.example_sign_images);
        renderNpcGroupPictures(container, 'Group members', group.example_member_images);
        network.setOptions({interaction: {keyboard: false}});
        if (!npcGroupDialog.open) npcGroupDialog.showModal();
        npcGroupDialog.scrollTop = 0;
    }
    function setupNpcGroupDetails() {
        npcGroupDialog = document.createElement('dialog');
        npcGroupDialog.id = 'map-npc-group-details';
        npcGroupDialog.setAttribute('aria-labelledby', 'map-npc-group-title');
        npcGroupDialog.innerHTML = `<div class="map-dialog-header"><div class="map-dialog-heading">
            <h2 id="map-npc-group-title"></h2></div><div class="map-dialog-actions">
            <button id="map-npc-group-close" type="button" autofocus>Close details</button></div></div>
            <div id="map-npc-group-content" class="map-dialog-body"></div>`;
        document.body.append(npcGroupDialog);
        document.getElementById('map-npc-group-close').addEventListener('click', () => npcGroupDialog.close());
        npcGroupDialog.addEventListener('keydown', event => trapDialogFocus(event, npcGroupDialog));
        npcGroupDialog.addEventListener('click', event => dismissOnBackdrop(event, npcGroupDialog));
        npcGroupDialog.addEventListener('close', () => {
            if (imagePreview.open) imagePreview.close();
            restoreViewerKeyboard();
        });
    }
    function renderNpcGroupList() {
        clearPictureTimers(additionalDialog);
        const container = document.getElementById('map-additional-content');
        container.innerHTML = '<h3 id="map-npc-group-list-title">NPC Groups</h3>';
        if (!npcGroups.size) {
            const empty = document.createElement('p');
            empty.textContent = 'No NPC groups have been recorded.';
            container.append(empty);
        }
        for (const group of npcGroups.values()) {
            const card = document.createElement('article');
            card.className = 'map-npc-group-card';
            const picture = rotatingPicture([...group.example_sign_images, ...group.example_member_images],
                additionalDialog, 'Group example');
            if (picture) card.append(picture);
            const content = document.createElement('div');
            const title = document.createElement('h4');
            title.append(groupButton(group));
            content.append(title);
            npcGroupSummaryFields.forEach(key => appendField(content, key, group[key]));
            const details = document.createElement('button');
            details.type = 'button';
            details.textContent = 'Details';
            details.setAttribute('aria-label', `Details for ${title.textContent}`);
            details.setAttribute('aria-haspopup', 'dialog');
            details.addEventListener('click', () => showNpcGroupDetails(group));
            content.append(details);
            card.append(content);
            container.append(card);
        }
        additionalDialog.scrollTop = 0;
        if (additionalDialog.open) document.getElementById('map-additional-npc-groups').focus();
    }
    function showAdditionalInformation() {
        hideTooltip();
        renderNpcGroupList();
        network.setOptions({interaction: {keyboard: false}});
        if (!additionalDialog.open) additionalDialog.showModal();
    }
    function setupAdditionalInformation() {
        additionalDialog = document.createElement('dialog');
        additionalDialog.id = 'map-additional-info';
        additionalDialog.setAttribute('aria-labelledby', 'map-additional-title');
        additionalDialog.innerHTML = `<div class="map-dialog-header"><h2 id="map-additional-title">Additional Information</h2>
            <button id="map-additional-close" type="button" autofocus>Close</button></div>
            <nav class="map-additional-sections" aria-label="Additional information sections">
                <button id="map-additional-npc-groups" type="button" aria-current="page">NPC Groups</button></nav>
            <div id="map-additional-content"></div>`;
        document.body.append(additionalDialog);
        document.getElementById('map-additional-open').addEventListener('click', () => showAdditionalInformation());
        document.getElementById('map-additional-close').addEventListener('click', () => additionalDialog.close());
        document.getElementById('map-additional-npc-groups').addEventListener('click', renderNpcGroupList);
        additionalDialog.addEventListener('keydown', event => trapDialogFocus(event, additionalDialog));
        additionalDialog.addEventListener('click', event => dismissOnBackdrop(event, additionalDialog));
        additionalDialog.addEventListener('close', () => {
            clearPictureTimers(additionalDialog);
            restoreViewerKeyboard();
        });
    }
    function openImagePreview(url, alt) {
        const enlarged = document.getElementById('map-image-preview-image');
        enlarged.alt = alt;
        enlarged.src = url;
        imagePreview.showModal();
    }
    function setupImagePreview() {
        const preview = document.createElement('dialog');
        imagePreview = preview;
        preview.id = 'map-image-preview';
        preview.setAttribute('aria-label', 'Full-screen image preview');
        preview.innerHTML = `<button id="map-image-preview-close" type="button" autofocus>Close image</button>
            <img id="map-image-preview-image" alt="">`;
        document.body.append(preview);
        document.getElementById('map-detail-image-open').addEventListener('click', () => {
            const image = document.getElementById('map-detail-image');
            if (image.hidden) return;
            openImagePreview(image.src, image.alt);
        });
        const close = document.getElementById('map-image-preview-close');
        close.addEventListener('click', () => preview.close());
        preview.addEventListener('keydown', event => {
            if (event.key === 'Tab') { event.preventDefault(); close.focus(); }
        });
        preview.addEventListener('click', event => {
            if (event.target === preview) preview.close();
        });
        dialog.addEventListener('close', () => { if (preview.open) preview.close(); });
    }
    function setupDetails() {
        dialog = document.createElement('dialog');
        dialog.id = 'map-details';
        dialog.setAttribute('aria-labelledby', 'map-detail-title');
        dialog.innerHTML = `<div class="map-dialog-header"><div class="map-dialog-heading"><div id="map-detail-kind"></div>
            <h2 id="map-detail-title"></h2></div><div class="map-dialog-actions"><div id="map-detail-appearance"></div>
            <button id="map-detail-close" type="button" autofocus>Close</button></div></div>
            <div class="map-dialog-body"><section id="map-detail-gallery" aria-label="Pictures">
            <figure id="map-detail-figure"><button id="map-detail-image-open" type="button"
            aria-label="View image full screen" title="View image full screen"><img id="map-detail-image" alt=""></button>
            <div id="map-image-fallback" hidden>Image unavailable</div>
            <figcaption id="map-detail-caption"></figcaption></figure><div id="map-gallery-thumbnails"></div>
            <details id="map-image-details" class="map-image-metadata"><summary>Image details</summary>
            <div id="map-image-metadata"></div></details></section><section aria-label="Object information">
            <div id="map-detail-fields"></div></section></div>`;
        document.body.append(dialog);
        setupImagePreview();
        document.getElementById('map-detail-close').addEventListener('click', () => dialog.close());
        dialog.addEventListener('keydown', event => trapDialogFocus(event, dialog));
        dialog.addEventListener('click', event => dismissOnBackdrop(event, dialog));
        dialog.addEventListener('close', () => {
            clearPictureTimers(dialog);
            appearanceNetwork?.destroy(); appearanceNetwork = null;
            restoreViewerKeyboard();
            previousFocus?.focus({preventScroll: true});
        });
        viewerKeyboard = network.interactionHandler.options.keyboard.enabled;
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
            clearPictureTimers(dialog);
            fields.replaceChildren();
            const keys = [...fieldOrder.filter(key => key in detail.fields),
                ...Object.keys(detail.fields).filter(key => !fieldOrder.includes(key))];
            for (const key of keys) {
                if (detail.kind === 'room' && key === 'name') continue;
                if (detail.kind === 'room' && key === 'details') appendRoomDetails(fields, detail.fields.details);
                else if (!hiddenFields.has(key)) appendField(fields, key, detail.fields[key], detail.references[key]);
            }
            if (detail.members?.length) appendField(fields, 'Members', detail.members.join(', '));
            if (detail.occupants?.length) appendField(fields, 'Occupants', detail.occupants.join(', '));
            renderConnectionSigns(detail.fields.signs, fields, detail.references);
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
        setupAdditionalInformation();
        setupNpcGroupDetails();
        setupCustomTooltips();
        if (PF2E_MAP_TRACKER_DEFAULT_VIEW) network.moveTo({...PF2E_MAP_TRACKER_DEFAULT_VIEW, animation: false});
    }
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', setup);
    else setup();
})();
