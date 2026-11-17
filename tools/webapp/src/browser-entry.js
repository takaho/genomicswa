const winkNLP = require('wink-nlp');
const model = require('wink-eng-lite-web-model');
const { createExtractor, FEATURES } = require('./extractor');
let _ex = null;
window.StyleNLP = { get: () => (_ex = _ex || createExtractor(winkNLP(model))), FEATURES };
