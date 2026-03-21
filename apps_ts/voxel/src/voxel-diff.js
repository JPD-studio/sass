export function computeDiff(current, background) {
    const results = [];
    for (const [key, state] of current) {
        const bg = background.get(key);
        const backgroundMean = bg?.mean ?? 0;
        const delta = state.count - backgroundMean;
        if (delta > 0) {
            results.push({
                key,
                currentCount: state.count,
                backgroundMean,
                delta,
            });
        }
    }
    return results;
}
