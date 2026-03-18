export class AdaptiveStddevThreshold {
    sigma;
    constructor(sigma = 2.0) {
        this.sigma = sigma;
    }
    isIntrusion(delta, _bgMean, bgStddev) {
        if (bgStddev === 0)
            return delta > 0;
        return delta > this.sigma * bgStddev;
    }
}
