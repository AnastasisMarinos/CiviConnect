export const nameToken = /[\p{L}\p{M}\p{N}\p{Pc}]+/gu;
const foldText = text => text.toLowerCase().normalize("NFD").replace(/\p{M}/gu, "").replaceAll("ς", "σ");
// Fold common Greek case endings when comparing name tokens.
export const nameWord = word => foldText(word).replace(/ο[συ]$/, "ο").replace(/([αηιω])σ$/, "$1");
export const nameWords = text => (text.match(nameToken) || []).map(nameWord);
const withoutNickname = text => text.replace(/\s*\([^)]*\)/g, "").trim();
export const directoryNameWords = person => nameWords(withoutNickname(person.name));
export const surnameKey = person => nameWords(withoutNickname(person.name).split(/\s+/).at(-1)).join(" ");

function matchProfiles(people, words) {
    const key = words.join(" ");
    const fullName = people.filter(person => directoryNameWords(person).join(" ") === key
        || nameWords(person.name).join(" ") === key);
    if (fullName.length) return fullName;
    if (words.length === 2) {
        const reversed = [words[1], words[0]].join(" ");
        const matches = people.filter(person => directoryNameWords(person).join(" ") === reversed);
        if (matches.length) return matches;
    }
    const surnames = people.filter(person => surnameKey(person) === key);
    if (surnames.length || words.length !== 1) return surnames;
    return people.filter(person => person.status === "demo" && directoryNameWords(person).includes(key));
}

export function findProfileQuery(content, people) {
    const trimPunctuation = text => text.replace(/^[\s«“"']+|[\s»”"'.;!?;]+$/gu, "");
    const text = trimPunctuation(foldText(content)).replace(/\s+/g, " ");
    const profilePrefix = /^(?:(?:δειξε μου |βρεσ μου )?(?:το )?προφιλ(?: (?:του|τησ|για))?|profile(?: of)?) +/;
    const explicit = profilePrefix.test(text);
    const query = trimPunctuation(text.replace(profilePrefix, "")
        .replace(/^(?:(?:ποιοσ|ποια) ειναι|who is|δειξε μου|βρεσ μου|ψαχνω) +/, "")
        .replace(/^(?:ο|η|τον|την) +/, ""));
    const words = nameWords(query);
    const matches = words.length ? matchProfiles(people, words) : [];
    return matches.length || explicit ? matches : null;
}

export function searchDirectory(people, query) {
    const search = foldText(query.trim());
    if (!search) return people;
    const words = nameWords(withoutNickname(search));
    const phrase = words.join(" ");
    const exactIds = new Set(words.length ? matchProfiles(people, words).map(person => person.id) : []);
    return people.filter(person => exactIds.has(person.id)
        || foldText(person.name + " " + person.party).includes(search)
        || (phrase && directoryNameWords(person).join(" ").includes(phrase)));
}
