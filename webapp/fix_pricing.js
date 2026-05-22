// Update the renderPriceRange function
function renderPriceRange(pr) {
    const min = (pr.min_prompt + pr.min_completion) * 1000000;
    const max = (pr.max_prompt + pr.max_completion) * 1000000;
    if (min === 0 && max === 0) return 'FREE';
    if (min < 1) {
        return `$${min.toFixed(4)} - $${max.toFixed(4)}`;
    }
    return `$${min.toFixed(2)} - $${max.toFixed(2)}`;
}

// Update model pricing display
// In modal: $${(model.pricing.prompt * 1000000).toFixed(4)} / $${(model.pricing.completion * 1000000).toFixed(4)}

// Update price range in info grid
// $${(pr.min_prompt * 1000000).toFixed(4)} - $${(pr.max_prompt * 1000000).toFixed(4)}
