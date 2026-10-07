/* Source relationships operate on the draft, never on graph-generated IDs. */
window.MapEditorState = (() => {
    const kinds = ['rooms', 'character_groups', 'characters', 'connections', 'connectionStatus'];
    const labels = {rooms: 'Room', character_groups: 'Group', characters: 'Character',
        connections: 'Connection', connectionStatus: 'Connection status'};
    const clone = value => JSON.parse(JSON.stringify(value));
    function label(kind, object, index) {
        return object.name || object.description || (kind === 'connections'
            ? `${object.from} → ${object.to} (${index + 1})` : object.id);
    }
    function renameReferences(data, kind, previous, next) {
        if (!previous || previous === next) return;
        if (kind === 'rooms') {
            for (const group of data.character_groups || []) if (group.location === previous) group.location = next;
            for (const character of data.characters || []) if (character.location === previous) character.location = next;
            for (const connection of data.connections || []) {
                if (connection.from === previous) connection.from = next;
                if (connection.to === previous) connection.to = next;
            }
        } else if (kind === 'character_groups') {
            for (const character of data.characters || []) if (character.group === previous) character.group = next;
        } else if (kind === 'connectionStatus') {
            for (const connection of data.connections || []) if (connection.status === previous) connection.status = next;
        }
    }
    function dependencies(data, kind, id) {
        const matches = [];
        const collect = (collection, predicate) => (data[collection] || []).forEach((item, i) => {
            if (predicate(item)) matches.push(`${labels[collection]}: ${label(collection, item, i)}`);
        });
        if (kind === 'rooms') {
            collect('character_groups', item => item.location === id);
            collect('characters', item => item.location === id);
            collect('connections', item => item.from === id || item.to === id);
        } else if (kind === 'character_groups') {
            collect('characters', item => item.group === id);
        } else if (kind === 'connectionStatus') {
            collect('connections', item => item.status === id);
        }
        return matches;
    }
    function suggestId(data, kind, name) {
        const base = name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'new-object';
        const used = new Set((kind === 'connectionStatus' ? data.connectionStatus || []
            : [...data.rooms || [], ...data.character_groups || []]).map(item => item.id));
        if (kind === 'rooms') used.add('unknown');
        let id = base, suffix = 2;
        while (used.has(id)) id = `${base}-${suffix++}`;
        return id;
    }
    return {kinds, labels, clone, label, renameReferences, dependencies, suggestId};
})();
