function processData(items, multiplier) {
    const unusedMultiplier = multiplier * 2;
    return items.map(x => x + undefinedGlobal);
}

processData([1, 2, 3], 5);
