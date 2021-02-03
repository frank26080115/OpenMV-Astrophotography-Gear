"use strict";var iqwerty=iqwerty||{};iqwerty.toast=(function(){function Toast(){var _duration=4000;this.getDuration=function(){return _duration;};this.setDuration=function(time){_duration=time;return this;};var _toastStage=null;this.getToastStage=function(){return _toastStage;};this.setToastStage=function(toastStage){_toastStage=toastStage;return this;};var _text=null;this.getText=function(){return _text;};this.setText=function(text){_text=text;return this;};var _textStage=null;this.getTextStage=function(){return _textStage;};this.setTextStage=function(textStage){_textStage=textStage;return this;};this.stylized=false;};Toast.prototype.styleExists=false;Toast.prototype.initializeAnimations=function(){if(Toast.prototype.styleExists)return;var style=document.createElement("style");style.classList.add(iqwerty.toast.identifiers.CLASS_STYLESHEET);style.innerHTML="."+iqwerty.toast.identifiers.CLASS_SLIDE_IN+
"{opacity: 1; bottom: 10%;}"+
"."+iqwerty.toast.identifiers.CLASS_SLIDE_OUT+
"{opacity: 0; bottom: -10%;}"+
"."+iqwerty.toast.identifiers.CLASS_ANIMATED+
"{transition: opacity "+iqwerty.toast.style.TOAST_ANIMATION_SPEED+"ms, bottom "+iqwerty.toast.style.TOAST_ANIMATION_SPEED+"ms;}";document.head.appendChild(style);Toast.prototype.styleExists=true;};Toast.prototype.generate=function(){var toastStage=document.createElement("div");var textStage=document.createElement("span");textStage.innerHTML=this.getText();toastStage.appendChild(textStage);this.setToastStage(toastStage);this.setTextStage(textStage);this.initializeAnimations();return this;};Toast.prototype.show=function(){if(this.getToastStage()==null){this.generate();}
if(!this.stylized){this.stylize();}
var body=document.body;var before=body.firstChild;this.getToastStage().classList.add(iqwerty.toast.identifiers.CLASS_ANIMATED);this.getToastStage().classList.add(iqwerty.toast.identifiers.CLASS_SLIDE_OUT);body.insertBefore(this.getToastStage(),before);this.getToastStage().offsetHeight;this.getToastStage().classList.add(iqwerty.toast.identifiers.CLASS_SLIDE_IN);this.getToastStage().classList.remove(iqwerty.toast.identifiers.CLASS_SLIDE_OUT);setTimeout(this.hide.bind(this),this.getDuration());return this;};Toast.prototype.hide=function(){if(this.getToastStage()==null)return;this.getToastStage().classList.remove(iqwerty.toast.identifiers.CLASS_SLIDE_IN);this.getToastStage().classList.add(iqwerty.toast.identifiers.CLASS_SLIDE_OUT);setTimeout(function(){document.body.removeChild(this.getToastStage());this.setToastStage(null);this.setText(null);this.setTextStage(null);}.bind(this),iqwerty.toast.style.TOAST_ANIMATION_SPEED);return this;};Toast.prototype.stylize=function(style){if(this.getToastStage()==null){this.generate();}
var toastStage=this.getToastStage();toastStage.setAttribute("style",iqwerty.toast.style.defaultStyle);if(arguments.length==1){var s=Object.keys(style);s.forEach(function(value,index,array){toastStage.style[value]=style[value];});}
this.stylized=true;return this;};return{Toast:Toast,style:{defaultStyle:""+
"background: rgba(204, 140, 12, .92);"+
"box-shadow: 0 0 10px rgba(0, 0, 0, .8);"+
"z-index: 99999;"+
"border-radius: 3px;"+
"color: rgba(255, 255, 255, .9);"+
"padding: 10px 15px;"+
"max-width: 40%;"+
"word-break: keep-all;"+
"margin: 0 auto;"+
"font-size: 14pt;"+
"text-align: center;"+
"position: fixed;"+
"left: 0;"+
"right: 0;",TOAST_ANIMATION_SPEED:400},identifiers:{CLASS_STYLESHEET:"iqwerty_toast_stylesheet",CLASS_ANIMATED:"iqwerty_toast_animated",CLASS_SLIDE_IN:"iqwerty_toast_slide_in",CLASS_SLIDE_OUT:"iqwerty_toast_slide_out"}};})();