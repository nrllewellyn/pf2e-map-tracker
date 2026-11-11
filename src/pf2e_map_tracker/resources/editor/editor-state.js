/* Source relationships operate on the draft, never on graph-generated IDs. */
window.MapEditorState = (() => {
    const {parseHtml, roomSignTags, signGroup} = window.MapDetails;
    const kinds = ['rooms', 'character_groups', 'characters', 'connections', 'npc_groups', 'connectionStatus'];
    const labels = {rooms: 'Room', character_groups: 'Group', characters: 'Character',
        connections: 'Connection', npc_groups: 'NPC group', connectionStatus: 'Connection status'};
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
        } else if (kind === 'npc_groups') {
            for (const connection of data.connections || []) {
                for (const sign of connection.signs || []) if (sign.group === previous) sign.group = next;
            }
            for (const room of data.rooms || []) {
                if (!room.details) continue;
                const template = parseHtml(room.details);
                const tags = roomSignTags(template.content).filter(tag => signGroup(tag) === previous);
                if (!tags.length) continue;
                for (const tag of tags) tag.setAttribute('group', next);
                room.details = template.innerHTML;
            }
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
        } else if (kind === 'npc_groups') {
            collect('connections', item => (item.signs || []).some(sign => sign.group === id));
            collect('rooms', item => item.details && roomSignTags(parseHtml(item.details).content)
                .some(tag => signGroup(tag) === id));
        }
        return matches;
    }
    function suggestId(data, kind, name) {
        const base = name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'new-object';
        const used = new Set((['connectionStatus', 'npc_groups'].includes(kind) ? data[kind] || []
            : [...data.rooms || [], ...data.character_groups || []]).map(item => item.id));
        if (kind === 'rooms') used.add('unknown');
        let id = base, suffix = 2;
        while (used.has(id)) id = `${base}-${suffix++}`;
        return id;
    }
    return {kinds, labels, clone, label, renameReferences, dependencies, suggestId};
})();
