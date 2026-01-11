#include <metal_stdlib>
using namespace metal;

/**
 * Vector addition kernel
 * Computes c[i] = a[i] + b[i] for all elements
 */
kernel void vec_add(
    device const float *a [[buffer(0)]],
    device const float *b [[buffer(1)]],
    device float *c [[buffer(2)]],
    uint id [[thread_position_in_grid]]
) {
    c[id] = a[id] + b[id];
}