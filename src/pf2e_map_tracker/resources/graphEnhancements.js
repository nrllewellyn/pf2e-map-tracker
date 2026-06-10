const tooltip = document.createElement('div');
tooltip.id = 'custom-vis-tooltip';
Object.assign(tooltip.style, {
    position: 'absolute',
    visibility: 'hidden',
    padding: '8px 12px',
    backgroundColor: 'rgba(30, 30, 50, 0.96)',
    color: '#f0f0ff',
    border: '1px solid #666',
    borderRadius: '6px',
    maxWidth: '420px',
    fontSize: '13px',
    lineHeight: '1.5',
    pointerEvents: 'none',
    zIndex: '9999',
    boxShadow: '0 4px 12px rgba(0,0,0,0.4)'
});
document.body.appendChild(tooltip);

function showTooltip(htmlContent, x, y) {
    if (!htmlContent) {
        tooltip.style.visibility = 'hidden';
        return;
    }
    tooltip.innerHTML = htmlContent.replace(/\n/g, '<br>');
    tooltip.style.left = (x + 20) + 'px';
    tooltip.style.top = (y + 20) + 'px';
    tooltip.style.visibility = 'visible';
}

function hideTooltip() {
    tooltip.style.visibility = 'hidden';
}

function setCharacterVisibility(visibility) {
    const tooltipProperty = 'tooltip_' + visibility;
    const updatedNodes = nodes.get().map(function (node) {
        if (node.node_type === 'character') {
            return {id: node.id, hidden: visibility !== 'show_all'};
        }
        if (node.node_type === 'character_group') {
            return {id: node.id, hidden: visibility === 'hidden', title: node[tooltipProperty]};
        }
        if (node.node_type === 'room') {
            return {id: node.id, hidden: false, title: node[tooltipProperty]};
        }
        return {id: node.id, hidden: false};
    });
    hideTooltip();
    nodes.update(updatedNodes);
}

function setupNodeSelectorLabels() {
    if (!window.nodes) {
        setTimeout(setupNodeSelectorLabels, 100);
        return;
    }
    const nodeSelect = document.getElementById('select-node');
    if (!nodeSelect || nodeSelect.dataset.displayLabelsApplied) {
        return;
    }
    nodeSelect.options[0].textContent = 'Select a Node';
    Array.from(nodeSelect.options).slice(1).forEach(function (option) {
        const node = nodes.get(option.value);
        if (node?.label) {
            option.textContent = node.label;
        }
    });
    nodeSelect.dataset.displayLabelsApplied = 'true';
}

function setupCharacterVisibility() {
    if (!window.network || !window.nodes) {
        setTimeout(setupCharacterVisibility, 100);
        return;
    }
    const selectMenu = document.getElementById('select-menu');
    if (!selectMenu || document.getElementById('character-visibility')) {
        return;
    }
    const controlRow = document.createElement('div');
    controlRow.className = 'd-flex align-items-end justify-content-between';
    controlRow.innerHTML = `
    <div class="pb-2 text-left" style="width: 320px;">
      <label for="character-visibility" class="form-label mb-1">Character Visibility</label>
      <select id="character-visibility" class="form-select" aria-label="Character Visibility">
        <option value="hidden">Hidden</option>
        <option value="groups_only" selected>Groups Only</option>
        <option value="show_all">Show All</option>
      </select>
    </div>
    <div class="pb-2 text-right" style="margin-left: auto;">
      <div id="program-version"></div>
      <div id="build-date"></div>
    </div>`;
    selectMenu.prepend(controlRow);
    document.getElementById('program-version').textContent =
        'Version ' + PF2E_MAP_TRACKER_BUILD.version;
    document.getElementById('build-date').textContent =
        'Built ' + PF2E_MAP_TRACKER_BUILD.builtAt;
    const visibilitySelect = document.getElementById('character-visibility');
    visibilitySelect.addEventListener('change', function (event) {
        setCharacterVisibility(event.target.value);
    });
    setCharacterVisibility(visibilitySelect.value);
}

function setupCustomTooltips() {
    if (!window.network) {
        setTimeout(setupCustomTooltips, 100);
        return;
    }
    network.on('hoverNode', function (params) {
        const node = network.body.nodes[params.node];
        if (node?.options?.title) {
            showTooltip(node.options.title, params.event.pageX, params.event.pageY);
        }
    });
    network.on('blurNode', hideTooltip);
    network.on('hoverEdge', function (params) {
        const edge = network.body.edges[params.edge];
        if (edge?.options?.title) {
            showTooltip(edge.options.title, params.event.pageX, params.event.pageY);
        }
    });
    network.on('blurEdge', hideTooltip);
}

if (document.readyState === 'complete') {
    setupCustomTooltips();
    setupCharacterVisibility();
    setupNodeSelectorLabels();
} else {
    document.addEventListener('DOMContentLoaded', setupCustomTooltips);
    document.addEventListener('DOMContentLoaded', setupCharacterVisibility);
    document.addEventListener('DOMContentLoaded', setupNodeSelectorLabels);
}
