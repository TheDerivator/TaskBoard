/** People lanes (pure): each person's lead and helping cards, in team rank order. */

/**
 * @param {object[]} people  active people, in display order
 * @param {object[]} tasks   visible tasks in rank order (already filtered)
 * @param {{leadOnly: boolean}} options
 * @returns {Array<{person: object, lead: number, helping: number, cards: Array<{task: object, role: "lead"|"helping"}>}>}
 */
export function buildLanes(people, tasks, { leadOnly = false } = {}) {
  return people.map((person) => {
    let lead = 0;
    let helping = 0;
    const cards = [];
    for (const task of tasks) {
      if (task.lead_id === person.id) {
        lead += 1;
        cards.push({ task, role: "lead" });
      } else if (task.helper_ids.includes(person.id)) {
        helping += 1;
        if (!leadOnly) cards.push({ task, role: "helping" });
      }
    }
    return { person, lead, helping, cards };
  });
}
