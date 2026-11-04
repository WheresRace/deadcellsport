#include <AL/al.h>
#include <AL/alc.h>
typedef void (*LPALCDEVICEPAUSESOFT)(ALCdevice *device);
typedef void (*LPALCDEVICERESUMESOFT)(ALCdevice *device);
typedef const ALCchar *(*LPALCGETSTRINGISOFT)(ALCdevice *device, ALCenum paramName, ALCsizei index);
typedef ALCboolean (*LPALCRESETDEVICESOFT)(ALCdevice *device, const ALCint *attribs);
