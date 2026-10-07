/* Local editor: valid draft, pending form, and saved file are separate states. */
(() => {
    'use strict';
    const {kinds, labels, clone, label, renameReferences, dependencies, suggestId} = window.MapEditorState;
    const $ = id => document.getElementById(id);
    const state = {data: null, saved: '', revision: '', schema: null, selection: null,
        formDirty: false, busy: false, conflict: false, network: null, nodes: null, edges: null};
    window.mapEditor = state;
    const definitions = {rooms: 'Room', character_groups: 'CharacterGroup', characters: 'Character',
        connections: 'Connection', connectionStatus: 'ConnectionStatus'};
    const fields = {
        rooms: ['id', 'name', 'position', 'color', 'shape', 'notes'],
        character_groups: ['id', 'name', 'location', 'defaultPosition', 'color', 'shape'],
        characters: ['name', 'ancestry', 'class', 'placement', 'defaultPosition', 'color', 'shape',
            'physical_description', 'personality', 'other_details'],
        connections: ['from', 'to', 'status', 'direction', 'name', 'notes'],
        connectionStatus: ['id', 'description', 'display_color', 'line_style']
    };
    const fieldLabels = {id: 'ID', name: 'Name', ancestry: 'Ancestry', class: 'Class', location: 'Room',
        group: 'Group', color: 'Color', shape: 'Shape', notes: 'Notes (HTML)', from: 'From room',
        to: 'To room', status: 'Connection status', direction: 'Direction', description: 'Description',
        display_color: 'Line color', line_style: 'Line style', physical_description: 'Physical description (HTML)',
        personality: 'Personality (HTML)', other_details: 'Other details (HTML)'};
    const htmlFields = new Set(['notes', 'physical_description', 'personality', 'other_details']);
    const draggableKinds = new Set(['rooms', 'character_groups', 'characters']);

    function notice(message, error = false) {
        $('notice').textContent = message;
        $('notice').classList.toggle('error', error);
    }
    function dirty() { return !!state.data && JSON.stringify(state.data) !== state.saved; }
    function updateControls() {
        $('save-state').textContent = state.busy ? 'Working…' : state.conflict ? 'File changed outside editor'
            : dirty() || state.formDirty ? 'Unsaved changes' : 'All changes saved';
        for (const id of ['save', 'rebuild', 'set-default-view']) $(id).disabled = state.busy || !state.data || state.conflict;
        for (const id of ['add', 'apply', 'delete', 'cancel']) $(id).disabled = state.busy || !state.data;
        $('reload').disabled = state.busy;
        $('object-form').inert = state.busy;
    }
    async function api(path, data, method = 'POST') {
        const response = await fetch(path, data === undefined ? {} : {
            method, headers: {'Content-Type': 'application/json', 'X-Map-Editor': '1'},
            body: JSON.stringify(data)
        });
        const result = await response.json();
        if (!response.ok) {
            if (response.status === 409) state.conflict = true;
            const details = result.errors || (Array.isArray(result.detail) ? result.detail : []);
            const message = [result.message || 'Request failed.', ...details.map(error =>
                `${error.loc.join('.') || 'Map'}: ${error.msg}`), result.error || ''].filter(Boolean).join('\n');
            const error = new Error(message);
            error.result = result;
            throw error;
        }
        return result;
    }
    async function run(action) {
        if (state.busy) return;
        state.busy = true;
        updateControls();
        try { await action(); }
        catch (error) { notice(error.message, true); }
        finally { state.busy = false; updateControls(); }
    }
    function confirmFormDiscard() {
        return !state.formDirty || confirm('Discard the changes in this form? Applied preview changes will stay.');
    }
    function clearForm() {
        state.selection = null;
        state.formDirty = false;
        $('object-form').hidden = true;
        $('cancel').hidden = true;
        $('form-title').textContent = 'Select an object';
        $('form-help').textContent = 'Choose an object on the graph or in the list, or add something new.';
        $('form-errors').textContent = '';
    }
    function renderList() {
        const search = $('search').value.trim().toLowerCase();
        $('object-list').replaceChildren();
        for (const kind of kinds) {
            const items = state.data?.[kind] || [];
            const section = document.createElement('section');
            section.className = 'object-section';
            const heading = document.createElement('h3');
            heading.textContent = `${labels[kind]}${kind === 'connectionStatus' ? 'es' : 's'} · ${items.length}`;
            section.append(heading);
            let count = 0;
            items.forEach((object, index) => {
                const title = label(kind, object, index);
                if (!`${title} ${object.id || ''} ${object.from || ''} ${object.to || ''}`.toLowerCase().includes(search)) return;
                count++;
                const button = document.createElement('button');
                button.type = 'button';
                button.className = 'object-item';
                button.dataset.kind = kind;
                button.dataset.index = index;
                button.classList.toggle('selected', state.selection?.kind === kind && state.selection.index === index);
                button.textContent = title;
                if (object.id) {
                    const small = document.createElement('small');
                    small.textContent = object.id;
                    button.append(small);
                }
                button.addEventListener('click', () => select({kind, index}));
                section.append(button);
            });
            if (count) $('object-list').append(section);
        }
        $('map-count').textContent = `${state.data?.rooms?.length || 0} rooms · ${state.data?.connections?.length || 0} connections`;
    }
    function select(reference) {
        if (state.busy || !confirmFormDiscard()) return;
        state.selection = {...reference};
        state.formDirty = false;
        renderForm(state.data[reference.kind][reference.index]);
        renderList();
        updateControls();
    }
    function htmlDocument(html) {
        return `<html><head><meta charset="utf-8"><style>body{font:13px/1.5 system-ui;color:#e7edf6;background:#222;padding:8px;margin:0;overflow-wrap:anywhere}a{color:#70d6c7}img{max-width:100%}</style></head><body>${html}</body></html>`;
    }
    function choiceValues(field) {
        if (['location', 'from', 'to'].includes(field)) {
            const rooms = (state.data.rooms || []).map(item => [item.id, `${item.name} (${item.id})`]);
            if (field !== 'location') rooms.push(['unknown', 'Unknown room']);
            return rooms;
        }
        if (field === 'group') return (state.data.character_groups || []).map(item => [item.id, `${item.name} (${item.id})`]);
        if (field === 'status') return (state.data.connectionStatus || []).map(item => [item.id, `${item.description} (${item.id})`]);
        const property = state.schema.$defs[definitions[state.selection.kind]].properties[field];
        const enumeration = property?.enum || state.schema.$defs[property?.$ref?.split('/').pop()]?.enum;
        return enumeration?.map(value => [value, value]);
    }
    function addField(field, value, required = false, container = $('fields')) {
        const wrapper = document.createElement('label');
        wrapper.className = 'field';
        const title = document.createElement('span');
        title.className = 'field-label';
        title.textContent = `${fieldLabels[field] || field}${required ? ' *' : ''}`;
        wrapper.append(title);
        const choices = choiceValues(field);
        let control;
        if (choices) {
            control = document.createElement('select');
            const property = state.schema.$defs[definitions[state.selection.kind]].properties[field];
            control.add(new Option(required ? 'Choose…' : `Default${property?.default ? ` (${property.default})` : ''}`, ''));
            choices.forEach(([id, text]) => control.add(new Option(text, id)));
        } else control = document.createElement(htmlFields.has(field) ? 'textarea' : 'input');
        control.name = field;
        control.id = `field-${field}`;
        control.required = required;
        control.value = value ?? '';
        if (field === 'id') {
            control.pattern = '[a-z0-9]+(?:-[a-z0-9]+)*';
            control.title = 'Lowercase letters and digits separated by single hyphens';
        }
        if (field === 'color' || field === 'display_color') {
            const row = document.createElement('span');
            row.className = 'color-row';
            control.type = 'text';
            control.placeholder = 'Default color';
            const picker = document.createElement('input');
            picker.type = 'color';
            picker.setAttribute('aria-label', `Choose ${fieldLabels[field].toLowerCase()}`);
            picker.value = /^#[0-9a-f]{6}$/i.test(control.value) ? control.value : '#3175cf';
            picker.addEventListener('input', () => { control.value = picker.value; markFormDirty(); });
            control.addEventListener('input', () => {
                if (/^#[0-9a-f]{6}$/i.test(control.value)) picker.value = control.value;
            });
            const reset = document.createElement('button');
            reset.type = 'button';
            reset.textContent = 'Clear';
            reset.addEventListener('click', () => { control.value = ''; markFormDirty(); });
            row.append(control, picker, reset);
            wrapper.append(row);
        } else wrapper.append(control);
        if (htmlFields.has(field)) {
            const preview = document.createElement('iframe');
            preview.className = 'html-preview';
            preview.title = `${fieldLabels[field]} preview`;
            preview.setAttribute('sandbox', '');
            preview.srcdoc = htmlDocument(control.value);
            control.addEventListener('input', () => { preview.srcdoc = htmlDocument(control.value); });
            wrapper.append(preview);
        }
        container.append(wrapper);
        return control;
    }
    function renderForm(object) {
        const {kind, index} = state.selection;
        const definition = state.schema.$defs[definitions[kind]];
        $('form-title').textContent = index === null ? `New ${labels[kind].toLowerCase()}` : `Edit ${labels[kind].toLowerCase()}`;
        $('form-help').textContent = 'Apply updates the preview. Save writes the map file. * Required field.';
        $('object-form').hidden = false;
        $('cancel').hidden = false;
        $('delete').hidden = index === null;
        $('form-errors').textContent = '';
        $('fields').replaceChildren();
        for (const field of fields[kind]) {
            if (field === 'position' || field === 'defaultPosition') {
                const optional = field === 'defaultPosition';
                if (optional) {
                    const help = document.createElement('p');
                    help.className = 'muted';
                    help.textContent = 'Default position: drag this node or enter coordinates. Physics starts here; leave both blank for automatic placement.';
                    $('fields').append(help);
                }
                const row = document.createElement('div');
                row.className = 'coordinate-row';
                $('fields').append(row);
                for (const axis of ['x', 'y']) {
                    const input = addField(axis, object[field]?.[axis], !optional, row);
                    input.type = 'number';
                    input.step = 'any';
                }
                if (optional) {
                    const reset = document.createElement('button');
                    reset.type = 'button';
                    reset.id = 'clear-default-position';
                    reset.textContent = 'Use automatic position';
                    reset.addEventListener('click', () => {
                        $('field-x').value = '';
                        $('field-y').value = '';
                        markFormDirty();
                    });
                    $('fields').append(reset);
                }
            } else if (field === 'placement') {
                const wrapper = document.createElement('label');
                wrapper.className = 'field';
                wrapper.textContent = 'Placement *';
                const mode = document.createElement('select');
                mode.id = 'placement-mode';
                mode.add(new Option('In a room', 'location'));
                mode.add(new Option('In a group', 'group'));
                mode.value = object.group != null ? 'group' : 'location';
                wrapper.append(mode);
                $('fields').append(wrapper);
                const target = document.createElement('div');
                $('fields').append(target);
                const placementField = () => {
                    target.replaceChildren();
                    addField(mode.value, object[mode.value], true, target);
                };
                placementField();
                mode.addEventListener('change', placementField);
            } else addField(field, object[field], definition.required.includes(field));
        }
        if (index === null && $('field-id')) {
            let manualId = false;
            $('field-id').addEventListener('input', () => { manualId = true; });
            const name = $('field-name') || $('field-description');
            name?.addEventListener('input', () => {
                if (!manualId) $('field-id').value = suggestId(state.data, kind, name.value);
            });
        }
    }
    function markFormDirty() { state.formDirty = true; updateControls(); }
    function readForm() {
        const {kind, index} = state.selection;
        const object = index === null ? {} : clone(state.data[kind][index]);
        const required = state.schema.$defs[definitions[kind]].required;
        for (const field of fields[kind]) {
            if (field === 'position' || field === 'defaultPosition') {
                if (field === 'defaultPosition' && $('field-x').value === '' && $('field-y').value === '') {
                    delete object.defaultPosition;
                    continue;
                }
                const x = $('field-x').valueAsNumber, y = $('field-y').valueAsNumber;
                if (!Number.isFinite(x) || !Number.isFinite(y)) throw new Error('Position requires two finite coordinates.');
                object[field] = {x, y};
            } else if (field === 'placement') {
                delete object.location;
                delete object.group;
                const mode = $('placement-mode').value;
                object[mode] = $(`field-${mode}`).value;
            } else {
                const value = $(`field-${field}`).value;
                if (value === '' && !required.includes(field)) {
                    if (object[field] !== '') delete object[field];
                } else object[field] = value;
            }
        }
        return object;
    }
    async function validateDraft(candidate) {
        return await api('/api/preview', {data: candidate});
    }
    async function commitDraft(candidate, selection = state.selection) {
        const result = await validateDraft(candidate);
        state.data = result.data;
        state.selection = selection;
        state.formDirty = false;
        renderGraph(result.graph);
        renderList();
        if (selection) renderForm(state.data[selection.kind][selection.index]);
        else clearForm();
        updateControls();
    }
    async function applyForm() {
        if (!state.selection) return;
        if (!$('object-form').reportValidity()) throw new Error('Complete the required fields before applying or saving.');
        try {
            const object = readForm();
            const candidate = clone(state.data);
            const {kind, index} = state.selection;
            if (index === null) {
                candidate[kind] ||= [];
                candidate[kind].push(object);
            } else {
                renameReferences(candidate, kind, candidate[kind][index].id, object.id);
                candidate[kind][index] = object;
            }
            const selection = {kind, index: index === null ? candidate[kind].length - 1 : index};
            await commitDraft(candidate, selection);
            notice('Preview updated. Save when you are ready.');
        } catch (error) {
            $('form-errors').textContent = error.message;
            throw error;
        }
    }
    function showTooltip(html, event) {
        if (!html) return;
        const tooltip = $('graph-tooltip');
        tooltip.srcdoc = htmlDocument(html.replace(/\n/g, '<br>'));
        tooltip.style.left = `${Math.max(5, Math.min(event.clientX + 16, innerWidth - 350))}px`;
        tooltip.style.top = `${Math.max(5, Math.min(event.clientY + 16, innerHeight - 210))}px`;
        tooltip.hidden = false;
    }
    function applyVisibility() {
        if (!state.nodes) return;
        const visibility = $('visibility').value;
        state.nodes.update(state.nodes.get().map(node => {
            const hidden = node.node_type === 'character' ? visibility !== 'show_all'
                : node.node_type === 'character_group' && visibility === 'hidden';
            return {id: node.id, hidden,
                tooltip: node[`tooltip_${visibility}`] || node.baseTooltip};
        }));
        $('graph-tooltip').hidden = true;
    }
    function renderGraph(graph, preservePositions = true) {
        $('graph-tooltip').hidden = true;
        const positions = state.network?.getPositions() || {};
        const nodes = graph.nodes.map(node => {
            const editable = node.editorRef.kind === 'rooms';
            const reference = node.editorRef;
            const copy = {...node, baseTooltip: node.title, tooltip: node.title,
                seedPosition: {x: node.x, y: node.y},
                defaultPosition: state.data[reference.kind]?.[reference.index]?.defaultPosition ?? null};
            delete copy.title;
            if (preservePositions && !editable && positions[node.id] && state.nodes?.get(node.id)?.editorRef.kind === node.editorRef.kind) {
                // Renderer seeds remain authoritative after placement changes.
                const previous = state.nodes.get(node.id);
                if (previous.seedPosition.x === node.x && previous.seedPosition.y === node.y
                    && JSON.stringify(previous.defaultPosition) === JSON.stringify(copy.defaultPosition)) {
                    Object.assign(copy, positions[node.id]);
                }
            }
            return copy;
        });
        const edges = graph.edges.map(edge => {
            const copy = {...edge, tooltip: edge.title};
            delete copy.title;
            return copy;
        });
        const options = clone(graph.options);
        options.interaction.dragNodes = true;
        options.interaction.multiselect = false;
        // Satellite settling must not zoom the canvas while the author is editing.
        options.physics.stabilization.fit = false;
        // Draw while satellites settle instead of hiding the editor canvas during initialization.
        options.physics.stabilization.enabled = false;
        state.nodes = new vis.DataSet(nodes);
        state.edges = new vis.DataSet(edges);
        if (state.network) {
            const view = {position: state.network.getViewPosition(), scale: state.network.getScale()};
            // setData initializes physics and fits the graph even with stabilization.fit
            // disabled. Restore the author's view before the refreshed graph is drawn.
            state.network.setData({nodes: state.nodes, edges: state.edges});
            state.network.moveTo({...view, animation: false});
        }
        else {
            state.network = new vis.Network($('graph'), {nodes: state.nodes, edges: state.edges}, options);
            state.network.on('click', params => {
                const object = params.nodes.length ? state.nodes.get(params.nodes[0])
                    : params.edges.length ? state.edges.get(params.edges[0]) : null;
                if (object) select(object.editorRef);
            });
            let draggedPositions;
            let roomDrag = null;
            const shiftHeld = params => params.event?.srcEvent?.shiftKey ?? params.event?.shiftKey ?? false;
            function dragPosition(drag, free = drag.free) {
                const position = {x: drag.pointer.x + drag.offset.x, y: drag.pointer.y + drag.offset.y};
                if (!free) {
                    position.x = Math.round(position.x / 250) * 250;
                    position.y = Math.round(position.y / 250) * 250;
                }
                return position;
            }
            function updateDragPosition() {
                const drag = roomDrag;
                if (!drag) return;
                requestAnimationFrame(() => {
                    // Run after vis-network moves the node, using the original grab offset
                    // so snapping never accumulates rounding error as the pointer moves.
                    if (roomDrag !== drag) return;
                    const position = dragPosition(drag);
                    state.network.moveNode(drag.id, position.x, position.y);
                });
            }
            state.network.on('dragStart', params => {
                draggedPositions = state.network.getPositions(params.nodes);
                roomDrag = null;
                const node = params.nodes.length ? state.nodes.get(params.nodes[0]) : null;
                if (params.nodes.length) {
                    // Shift is the precision modifier for node drags, overriding vis's marquee.
                    state.network.body.selectionBox.show = false;
                }
                if (node?.editorRef.kind === 'rooms' && !state.busy) {
                    const pointer = params.pointer.canvas;
                    const origin = draggedPositions[node.id];
                    roomDrag = {id: node.id, pointer, free: shiftHeld(params),
                        offset: {x: origin.x - pointer.x, y: origin.y - pointer.y}};
                }
                // vis-network snapshots fixed flags after this event. Allow source nodes
                // to move during a drag, while virtual unknown rooms remain uneditable.
                state.nodes.update(params.nodes.map(id => ({id, ...draggedPositions[id],
                    fixed: draggableKinds.has(state.nodes.get(id).editorRef.kind) && !state.busy ? false : true})));
                $('graph-tooltip').hidden = true;
            });
            state.network.on('dragging', params => {
                if (!roomDrag) return;
                roomDrag.pointer = params.pointer.canvas;
                roomDrag.free = shiftHeld(params);
                updateDragPosition();
            });
            for (const type of ['keydown', 'keyup']) addEventListener(type, event => {
                if (event.key !== 'Shift' || !roomDrag) return;
                roomDrag.free = type === 'keydown';
                updateDragPosition();
            });
            state.network.on('dragEnd', params => {
                if (!params.nodes.length) return;
                const node = state.nodes.get(params.nodes[0]);
                if (roomDrag) roomDrag.pointer = params.pointer.canvas;
                const position = roomDrag?.id === node.id ? dragPosition(roomDrag, shiftHeld(params))
                    : state.network.getPositions([node.id])[node.id];
                roomDrag = null;
                const fixed = node.editorRef.kind === 'rooms' ? {x: true, y: true} : false;
                state.nodes.update({id: node.id, ...position, fixed});
                const restore = () => state.nodes.update({id: node.id, ...draggedPositions[node.id], fixed});
                if (state.busy || !draggableKinds.has(node.editorRef.kind) || !confirmFormDiscard()) { restore(); return; }
                run(async () => {
                    const candidate = clone(state.data);
                    const {kind, index} = node.editorRef;
                    const field = kind === 'rooms' ? 'position' : 'defaultPosition';
                    candidate[kind][index][field] = position;
                    try {
                        await commitDraft(candidate, node.editorRef);
                        notice(kind === 'rooms' ? 'Room position updated. Save to keep this arrangement.'
                            : 'Default position updated. Save to keep this starting position.');
                    } catch (error) { restore(); throw error; }
                });
            });
            state.network.on('hoverNode', params => showTooltip(state.nodes.get(params.node).tooltip, params.event));
            state.network.on('hoverEdge', params => showTooltip(state.edges.get(params.edge).tooltip, params.event));
            for (const event of ['blurNode', 'blurEdge', 'zoom']) state.network.on(event, () => { $('graph-tooltip').hidden = true; });
        }
        applyVisibility();
    }
    async function load() {
        const result = await api('/api/map');
        const preview = await validateDraft(result.data);
        state.data = preview.data;
        state.saved = JSON.stringify(state.data);
        state.revision = result.revision;
        state.schema = result.schema;
        state.conflict = false;
        clearForm();
        renderList();
        renderGraph(preview.graph, false);
        if (state.data.defaultView) state.network.moveTo({...state.data.defaultView, animation: false});
        else state.network.fit();
        $('file-path').textContent = result.input;
        $('file-path').title = `Map: ${result.input}\nOutput: ${result.output}`;
        notice('Map loaded. Select an object to start editing.');
    }
    async function save(rebuild) {
        if (state.formDirty || state.selection?.index === null) await applyForm();
        let result;
        try {
            result = await api(rebuild ? '/api/rebuild' : '/api/map',
                {data: state.data, revision: state.revision}, rebuild ? 'POST' : 'PUT');
        } catch (error) {
            if (error.result?.saved) {
                state.data = error.result.data;
                state.revision = error.result.revision;
                state.saved = JSON.stringify(state.data);
            }
            throw error;
        }
        state.data = result.data;
        state.revision = result.revision;
        state.saved = JSON.stringify(state.data);
        notice(result.message || 'Changes saved. Rebuild graph to update the HTML map.');
    }
    $('object-form').addEventListener('input', markFormDirty);
    $('object-form').addEventListener('change', markFormDirty);
    $('object-form').addEventListener('submit', event => { event.preventDefault(); run(applyForm); });
    $('search').addEventListener('input', renderList);
    $('visibility').addEventListener('change', applyVisibility);
    $('fit').addEventListener('click', () => state.network?.fit({animation: true}));
    $('set-default-view').addEventListener('click', () => {
        if (state.busy || !state.data || state.conflict || !state.network) return;
        state.data.defaultView = {
            position: state.network.getViewPosition(), scale: state.network.getScale()
        };
        updateControls();
        notice('Default view updated. Save to keep it, or Rebuild graph to update the HTML map too.');
    });
    $('save').addEventListener('click', () => run(() => save(false)));
    $('rebuild').addEventListener('click', () => run(() => save(true)));
    $('reload').addEventListener('click', () => {
        if ((dirty() || state.formDirty) && !confirm('Reload from disk and discard all unsaved changes?')) return;
        run(load);
    });
    $('cancel').addEventListener('click', () => {
        if (!confirmFormDiscard()) return;
        clearForm(); renderList(); updateControls();
    });
    $('add').addEventListener('click', () => {
        if (!confirmFormDiscard()) return;
        const kind = $('add-kind').value;
        const center = state.network?.getViewPosition() || {x: 0, y: 0};
        const object = kind === 'rooms' ? {position: center} : {};
        if (kind !== 'characters' && kind !== 'connections') object.id = suggestId(state.data, kind, `new-${labels[kind]}`);
        state.selection = {kind, index: null};
        renderForm(object); state.formDirty = true; renderList(); updateControls();
        ($('field-name') || $('field-description') || $('field-from'))?.focus();
    });
    $('delete').addEventListener('click', () => {
        const {kind, index} = state.selection;
        const object = state.data[kind][index];
        const dependents = dependencies(state.data, kind, object.id);
        if (dependents.length) {
            $('form-errors').textContent = `Reassign or remove these dependent objects first:\n${dependents.join('\n')}`;
            return;
        }
        if (!confirm(`Delete ${labels[kind].toLowerCase()} “${label(kind, object, index)}”?`)) return;
        run(async () => {
            const candidate = clone(state.data);
            candidate[kind].splice(index, 1);
            await commitDraft(candidate, null);
            notice('Object removed from preview. Save to keep this change.');
        });
    });
    addEventListener('beforeunload', event => {
        if (dirty() || state.formDirty) { event.preventDefault(); event.returnValue = ''; }
    });
    run(load);
})();
