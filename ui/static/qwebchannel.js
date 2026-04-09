/****************************************************************************
**
** Qt WebChannel 2.0.0
**
** This file is part of the QtWebChannel module of the Qt Toolkit.
**
****************************************************************************/

(function() {

    if (typeof qt !== "undefined" && qt.webChannelTransport) {
        // already loaded – do nothing
    }

    var WebChannelMessageTypes = {
        signal: 1,
        propertyUpdate: 2,
        init: 3,
        idle: 4,
        debug: 5,
        invokeMethod: 6,
        connectToSignal: 7,
        disconnectFromSignal: 8,
        setProperty: 9,
        response: 10
    };

    function wrapCallback(object, callback) {
        if (typeof callback !== "function")
            return null;
        return function() {
            callback.apply(object, arguments);
        };
    }

    function registerSignal(object, signalName) {
        object[signalName] = {
            connect: function(callback) {
                object.webChannel_.exec({
                    type: WebChannelMessageTypes.connectToSignal,
                    object: object.__id__,
                    signal: signalName
                }, wrapCallback(object, callback));
            },
            disconnect: function(callback) {
                object.webChannel_.exec({
                    type: WebChannelMessageTypes.disconnectFromSignal,
                    object: object.__id__,
                    signal: signalName
                }, wrapCallback(object, callback));
            }
        };
    }
    function registerProperty(object, propertyInfo) {
        var propertyIndex = propertyInfo.index;
        var notifySignal = propertyInfo.notify;
        var readOnly = propertyInfo.readOnly;
        var propertyName = propertyInfo.name;

        if (!readOnly) {
            Object.defineProperty(object, propertyName, {
                configurable: true,
                enumerable: true,
                get: function() {
                    return object.__propertyCache__[propertyIndex];
                },
                set: function(value) {
                    object.webChannel_.exec({
                        type: WebChannelMessageTypes.setProperty,
                        object: object.__id__,
                        property: propertyIndex,
                        value: value
                    });
                }
            });
        } else {
            Object.defineProperty(object, propertyName, {
                configurable: true,
                enumerable: true,
                get: function() {
                    return object.__propertyCache__[propertyIndex];
                }
            });
        }

        if (notifySignal) {
            registerSignal(object, notifySignal);
        }
    }

    function registerMethod(object, methodInfo) {
        object[methodInfo.name] = function() {
            var args = [];
            var callback;

            [].slice.call(arguments).forEach(function(arg) {
                if (typeof arg === "function") {
                    callback = wrapCallback(object, arg);
                } else {
                    args.push(arg);
                }
            });

            object.webChannel_.exec({
                type: WebChannelMessageTypes.invokeMethod,
                object: object.__id__,
                method: methodInfo.index,
                args: args
            }, callback);
        };
    }
    function registerSignal(object, signalInfo) {
        if (object[signalInfo.name]) {
            return;
        }

        object[signalInfo.name] = {
            connect: function(callback) {
                object.webChannel_.connectToSignal(object.__id__, signalInfo.index, callback);
            }
        };
    }

    function registerObject(channel, objectInfo) {
        if (channel.objects[objectInfo.id]) {
            return channel.objects[objectInfo.id];
        }

        var object = new QObject(objectInfo, channel);
        channel.objects[objectInfo.id] = object;

        return object;
    }

    function QObject(objectInfo, webChannel) {
        this.__id__ = objectInfo.id;
        this.webChannel_ = webChannel;
        this.__propertyCache__ = {};

        var object = this;

        objectInfo.properties.forEach(function(propertyInfo) {
            object.__propertyCache__[propertyInfo.index] = propertyInfo.value;
            registerProperty(object, propertyInfo);
        });

        objectInfo.methods.forEach(function(methodInfo) {
            registerMethod(object, methodInfo);
        });

        objectInfo.signals.forEach(function(signalInfo) {
            registerSignal(object, signalInfo);
        });
    }
    function WebChannel(transport, initCallback) {
        var channel = this;

        this.transport = transport;
        this.transport.send = this.transport.send || function() {};

        this.execCallbacks = {};
        this.objects = {};

        this.transport.onmessage = function(message) {
            var data = JSON.parse(message.data);
            handleMessage(data);
        };

        function handleMessage(message) {
            switch (message.type) {
                case WebChannelMessageTypes.signal:
                    handleSignal(message);
                    break;

                case WebChannelMessageTypes.response:
                    handleResponse(message);
                    break;

                case WebChannelMessageTypes.propertyUpdate:
                    handlePropertyUpdate(message);
                    break;

                case WebChannelMessageTypes.init:
                    handleInit(message);
                    break;

                default:
                    console.warn("Unknown WebChannel message", message);
            }
        }

        function handleSignal(message) {
            var object = channel.objects[message.object];
            if (!object) return;

            var signalHandlers = object[message.signal];
            if (!signalHandlers || !signalHandlers.connect) return;

            signalHandlers.connect(function() {}); // no-op wiring

            if (object[message.signal].__handlers__) {
                object[message.signal].__handlers__.forEach(function(handler) {
                    handler.apply(object, message.args);
                });
            }
        }

        function handleResponse(message) {
            var callback = channel.execCallbacks[message.id];
            if (callback) {
                delete channel.execCallbacks[message.id];
                callback(message.data);
            }
        }
        function handlePropertyUpdate(message) {
            Object.keys(message.data).forEach(function(objectId) {
                var object = channel.objects[objectId];
                if (!object) return;

                var properties = message.data[objectId];
                Object.keys(properties).forEach(function(propIndex) {
                    object.__propertyCache__[propIndex] = properties[propIndex];
                });
            });
        }

        function handleInit(message) {
            message.data.objects.forEach(function(objectInfo) {
                registerObject(channel, objectInfo);
            });

            if (initCallback) {
                initCallback(channel);
            }
        }

        this.exec = function(message, callback) {
            if (callback) {
                message.id = Math.random().toString(36).substr(2, 10);
                channel.execCallbacks[message.id] = callback;
            }

            channel.transport.postMessage(JSON.stringify(message));
        };

        this.connectToSignal = function(objectId, signalIndex, callback) {
            var object = channel.objects[objectId];
            if (!object[signalIndex].__handlers__) {
                object[signalIndex].__handlers__ = [];
            }
            object[signalIndex].__handlers__.push(callback);
        };
    }
    function registerObject(channel, data) {

        var object = {
            __id__: data.id,
            __propertyCache__: data.properties
        };

        // methods
        data.methods.forEach(function(methodInfo) {
            object[methodInfo.name] = function() {
                var args = Array.prototype.slice.call(arguments);
                return new Promise(function(resolve) {
                    channel.exec({
                        type: "invokeMethod",
                        object: data.id,
                        method: methodInfo.name,
                        args: args
                    }, resolve);
                });
            };
        });

        // signals
        data.signals.forEach(function(signalInfo) {
            object[signalInfo.name] = function() {};
        });

        channel.objects[data.id] = object;
    }

    window.QWebChannel = QWebChannel;
})();
