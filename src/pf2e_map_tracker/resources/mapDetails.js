/* Detail fields and sign cards shared by the viewer and the editor preview. */
window.MapDetails = (() => {
    'use strict';
    const signFields = {location: 'Location', description: 'Description', translation: 'Translation'};

    function hasContent(element) {
        return element.textContent.trim() || element.querySelector('img,video,audio,iframe,svg,canvas,object,embed');
    }
    function appendDetailField(container, label, renderValue) {
        const doc = container.ownerDocument;
        const dd = doc.createElement('dd');
        renderValue(dd);
        if (!hasContent(dd)) return;
        const dl = doc.createElement('dl');
        dl.className = 'map-detail-field';
        const dt = doc.createElement('dt');
        dt.textContent = label;
        dl.append(dt, dd);
        container.append(dl);
    }
    function createSignCard(doc, sign, index, {groupName, language, thumbnail}) {
        const card = doc.createElement('article');
        card.className = 'map-sign-card';
        card.setAttribute('aria-label', `Sign ${index + 1}`);
        if (thumbnail) card.append(thumbnail);
        const content = doc.createElement('div');
        if (groupName) {
            groupName.classList.add('map-sign-group');
            content.append(groupName);
        }
        if (language) appendDetailField(content, 'Language', dd => { dd.innerHTML = language.replace(/\n/g, '<br>'); });
        for (const [key, label] of Object.entries(signFields)) {
            if (sign[key]) appendDetailField(content, label, dd => { dd.innerHTML = sign[key]; });
        }
        card.append(content);
        return card;
    }

    function parseHtml(html) {
        const template = document.createElement('template');
        template.innerHTML = html;
        return template;
    }
    function roomSignTags(container) {
        return Array.from(container.children).filter(child => child.localName === 'map-sign');
    }
    function signGroup(tag) {
        return tag.getAttribute('group')?.trim() || '';
    }
    function readRoomSign(tag) {
        if (Array.from(tag.childNodes).some(node => node.nodeType === Node.TEXT_NODE && node.textContent.trim())) {
            return null;
        }
        const sign = {};
        for (const child of tag.children) {
            const fields = Object.keys(signFields).filter(key => child.hasAttribute(`data-${key}`));
            if (child.localName !== 'div' || fields.length !== 1) return null;
            const [key] = fields;
            if (key in sign) return null;
            sign[key] = hasContent(child) ? child.innerHTML : '';
        }
        return sign.description && sign.translation ? sign : null;
    }
    function renderRoomSigns(container, npcGroups, makeCard) {
        const tags = container.querySelectorAll('map-sign');
        if (!tags.length) return null;
        container.classList.add('map-room-details');
        const warnings = [];
        if (Array.from(tags).some(tag => tag.parentNode !== container)) {
            warnings.push('Place <map-sign> between paragraphs at the top level of room Details.');
        }
        roomSignTags(container).forEach((tag, index) => {
            const groupId = signGroup(tag);
            const group = npcGroups.get(groupId);
            if (!group) {
                warnings.push(groupId ? `Sign ${index + 1} uses an unknown NPC group ID “${groupId}”.`
                    : `Sign ${index + 1} needs an NPC group ID in its group attribute.`);
            }
            const sign = readRoomSign(tag);
            if (sign) tag.replaceWith(makeCard(sign, group, index));
            else warnings.push(`Sign ${index + 1} needs one <div data-description> and one <div data-translation> with content. A <div data-location> is optional.`);
        });
        return warnings;
    }

    return {hasContent, appendDetailField, createSignCard, parseHtml, roomSignTags, signGroup, renderRoomSigns};
})();
